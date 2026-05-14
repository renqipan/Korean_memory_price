from __future__ import annotations

import argparse
import os
from pathlib import Path

from .categories import DEFAULT_FETCH_HS_CODES, parse_memory_categories
from .charts import (
    render_category_price_trend_png,
    render_category_price_trends_png,
    render_memory_indicators_png,
    render_memory_score_png,
)
from .io_utils import read_trade_records, write_trade_records
from .kcs import KCSClient
from .metrics import (
    CATEGORY_INDEX_COLUMNS,
    INDEX_COLUMNS,
    UNIT_PRICE_COLUMNS,
    build_category_memory_indexes,
    build_memory_index,
    build_unit_price_rows,
    latest_summary,
)
from .prosperity import PROSPERITY_COLUMNS, build_prosperity_scores
from .trass import load_trass_export
from .utils import month_to_yymm, write_csv_rows


DEFAULT_HS_CODES = DEFAULT_FETCH_HS_CODES


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="korean-memory-price",
        description="Compute Korean memory export unit prices from KCS/TRASS data.",
    )
    subparsers = parser.add_subparsers(required=True)

    kcs_fetch = subparsers.add_parser("kcs-fetch", help="Fetch monthly HS data from KCS OpenAPI.")
    add_kcs_args(kcs_fetch)
    kcs_fetch.add_argument("--out", required=True, help="Output trade CSV path.")
    kcs_fetch.set_defaults(func=cmd_kcs_fetch)

    trass_import = subparsers.add_parser("trass-import", help="Import a TRASS CSV/XLSX export.")
    trass_import.add_argument("--file", required=True, help="TRASS export file path.")
    trass_import.add_argument("--out", required=True, help="Output trade CSV path.")
    trass_import.set_defaults(func=cmd_trass_import)

    price = subparsers.add_parser("price", help="Compute unit prices and memory price index.")
    price.add_argument("--input", nargs="+", required=True, help="Trade CSV files from kcs-fetch/trass-import.")
    price.add_argument("--out", required=True, help="Unit price CSV path.")
    price.add_argument("--index-out", required=True, help="Composite memory index CSV path.")
    price.add_argument("--score-out", help="Optional memory prosperity score CSV path.")
    price.add_argument("--category-index-out", help="Optional category-level price index CSV path.")
    add_category_args(price)
    price.set_defaults(func=cmd_price)

    chart = subparsers.add_parser("chart", help="Render PNG charts for memory prosperity.")
    chart.add_argument("--prosperity", required=True, help="memory_prosperity_score.csv path.")
    chart.add_argument("--category-index", help="memory_category_price_index.csv path.")
    chart.add_argument("--outdir", required=True, help="Chart output directory.")
    chart.set_defaults(func=cmd_chart)

    run = subparsers.add_parser("run", help="Run KCS fetch and memory prosperity calculation.")
    add_kcs_args(run)
    add_category_args(run)
    run.add_argument("--trass-file", action="append", default=[], help="Optional TRASS export file to merge.")
    run.add_argument("--no-charts", action="store_true", help="Do not render PNG charts.")
    run.add_argument("--outdir", required=True, help="Output directory.")
    run.set_defaults(func=cmd_run)
    return parser


def add_kcs_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", required=True, help="Start month, YYYYMM.")
    parser.add_argument(
        "--end",
        required=True,
        help="End month, YYYYMM, or latest. 'latest' probes KCS from the current month backward.",
    )
    parser.add_argument("--hs", action="append", default=[], help="HS/HSK code. Can be repeated.")
    parser.add_argument("--service-key", help="KCS/data.go.kr service key. Defaults to DATA_GO_KR_SERVICE_KEY.")
    parser.add_argument(
        "--encoded-key",
        action="store_true",
        help="Use when the service key is already URL-encoded.",
    )
    parser.add_argument(
        "--endpoint",
        choices=["data-go-kr", "legacy"],
        default="data-go-kr",
        help="KCS API endpoint style.",
    )


def add_category_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--category",
        action="append",
        default=[],
        help=(
            "Add a category as name=hs1,hs2 or name:Label=hs1,hs2. "
            "Defaults include DRAM/HBM, NAND/Flash, SSD, and Total memory."
        ),
    )


def cmd_kcs_fetch(args: argparse.Namespace) -> int:
    records = fetch_kcs_records(args)
    write_trade_records(records, args.out)
    print(f"Wrote {len(records)} KCS trade rows to {args.out}")
    return 0


def cmd_trass_import(args: argparse.Namespace) -> int:
    records = load_trass_export(args.file)
    write_trade_records(records, args.out)
    print(f"Wrote {len(records)} TRASS trade rows to {args.out}")
    return 0


def cmd_price(args: argparse.Namespace) -> int:
    records = read_trade_records(args.input)
    unit_rows = build_unit_price_rows(records)
    index_rows = build_memory_index(unit_rows)
    category_rows = build_category_memory_indexes(unit_rows, parse_categories(args))
    score_rows = build_prosperity_scores(index_rows)
    write_csv_rows(unit_rows, args.out, UNIT_PRICE_COLUMNS)
    write_csv_rows(index_rows, args.index_out, INDEX_COLUMNS)
    if args.category_index_out:
        write_csv_rows(category_rows, args.category_index_out, CATEGORY_INDEX_COLUMNS)
    if args.score_out:
        write_csv_rows(score_rows, args.score_out, PROSPERITY_COLUMNS)
    summary = latest_summary(index_rows)
    print(f"Wrote {len(unit_rows)} unit price rows to {args.out}")
    print(f"Wrote {len(index_rows)} memory index rows to {args.index_out}")
    if args.category_index_out:
        print(f"Wrote {len(category_rows)} category price index rows to {args.category_index_out}")
    if args.score_out:
        print(f"Wrote {len(score_rows)} memory prosperity score rows to {args.score_out}")
    if summary:
        print(
            "Latest memory index: "
            f"{summary.get('month')} index={summary.get('memory_index')} "
            f"3m={summary.get('memory_index_mom_3m_pct')} "
            f"yoy={summary.get('memory_index_yoy_pct')}"
        )
    return 0


def cmd_chart(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    prosperity_rows = _read_generic_csv(args.prosperity)
    score_path = outdir / "memory_prosperity_score.png"
    indicator_path = outdir / "memory_indicators.png"
    render_memory_score_png(prosperity_rows, score_path)
    render_memory_indicators_png(prosperity_rows, indicator_path)
    print(f"Wrote memory prosperity score chart to {score_path}")
    print(f"Wrote indicator chart to {indicator_path}")
    if args.category_index:
        category_rows = _read_generic_csv(args.category_index)
        category_trends_path = outdir / "memory_category_price_trends.png"
        render_category_price_trends_png(category_rows, category_trends_path)
        print(f"Wrote category price trend chart to {category_trends_path}")
        for category in sorted({str(row.get("category")) for row in category_rows if row.get("category")}):
            category_path = outdir / f"memory_price_trend_{category}.png"
            render_category_price_trend_png(category_rows, category, category_path)
            print(f"Wrote category price trend chart to {category_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    kcs_records = fetch_kcs_records(args)
    all_records = list(kcs_records)
    for trass_file in args.trass_file:
        all_records.extend(load_trass_export(trass_file))

    trade_path = outdir / "memory_trade.csv"
    unit_path = outdir / "memory_unit_prices.csv"
    index_path = outdir / "memory_price_index.csv"
    category_index_path = outdir / "memory_category_price_index.csv"
    score_path = outdir / "memory_prosperity_score.csv"
    chart_dir = outdir / "charts"

    write_trade_records(all_records, trade_path)
    unit_rows = build_unit_price_rows(all_records)
    index_rows = build_memory_index(unit_rows)
    category_rows = build_category_memory_indexes(unit_rows, parse_categories(args))
    score_rows = build_prosperity_scores(index_rows)
    write_csv_rows(unit_rows, unit_path, UNIT_PRICE_COLUMNS)
    write_csv_rows(index_rows, index_path, INDEX_COLUMNS)
    write_csv_rows(category_rows, category_index_path, CATEGORY_INDEX_COLUMNS)
    write_csv_rows(score_rows, score_path, PROSPERITY_COLUMNS)

    if not args.no_charts:
        chart_dir.mkdir(parents=True, exist_ok=True)
        render_memory_score_png(score_rows, chart_dir / "memory_prosperity_score.png")
        render_memory_indicators_png(score_rows, chart_dir / "memory_indicators.png")
        render_category_price_trends_png(category_rows, chart_dir / "memory_category_price_trends.png")
        for category in sorted({str(row.get("category")) for row in category_rows if row.get("category")}):
            render_category_price_trend_png(
                category_rows,
                category,
                chart_dir / f"memory_price_trend_{category}.png",
            )

    print(f"Wrote trade data to {trade_path}")
    print(f"Wrote unit prices to {unit_path}")
    print(f"Wrote memory index to {index_path}")
    print(f"Wrote category price index to {category_index_path}")
    print(f"Wrote memory prosperity score to {score_path}")
    if not args.no_charts:
        print(f"Wrote charts to {chart_dir}")
    return 0


def fetch_kcs_records(args: argparse.Namespace):
    service_key = (
        args.service_key
        or os.environ.get("DATA_GO_KR_SERVICE_KEY")
        or os.environ.get("KCS_SERVICE_KEY")
    )
    if not service_key:
        raise SystemExit("Missing service key. Set DATA_GO_KR_SERVICE_KEY or pass --service-key.")
    hs_codes = args.hs or DEFAULT_HS_CODES
    client = KCSClient(
        service_key=service_key,
        endpoint=args.endpoint,
        service_key_encoded=args.encoded_key,
    )
    start_yymm = month_to_yymm(args.start)
    end_yymm = resolve_end_yymm(args.end, client, hs_codes, start_yymm)
    if str(args.end).strip().lower() == "latest":
        print(f"Resolved latest available KCS month: {end_yymm}")
    return client.fetch_many(start_yymm, end_yymm, hs_codes)


def parse_categories(args: argparse.Namespace):
    try:
        return parse_memory_categories(getattr(args, "category", []))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def resolve_end_yymm(
    end: str,
    client: KCSClient,
    hs_codes: list[str],
    start_yymm: str,
) -> str:
    if str(end).strip().lower() != "latest":
        return month_to_yymm(end)
    return client.find_latest_available_month(hs_codes, start_month=start_yymm)


def _read_generic_csv(path: str | Path) -> list[dict[str, str]]:
    from .utils import read_csv_rows

    return read_csv_rows(path)


if __name__ == "__main__":
    raise SystemExit(main())
