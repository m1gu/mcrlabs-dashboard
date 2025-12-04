"""Data access helpers for entity detail endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from downloader_qbench_data.storage import Batch, Customer, Order, Sample, Test
from downloader_qbench_data.bans import is_banned
from ..schemas.entities import (
    OrderDetailResponse,
    OrderSampleItem,
    OrderSampleTestItem,
    SampleBatchItem,
    SampleDetailResponse,
    SampleTestItem,
    TestBatchItem,
    TestDetailResponse,
)

_WARNING_RATIO = 0.75


def _classify_sla(age_hours: float, sla_hours: float) -> str:
    if sla_hours <= 0:
        return "ok"
    if age_hours >= sla_hours:
        return "overdue"
    if age_hours >= sla_hours * _WARNING_RATIO:
        return "warning"
    return "ok"


def _age_hours(start: Optional[datetime], end: Optional[datetime] = None) -> float:
    if not start:
        return 0.0
    ref = end or datetime.utcnow()
    return max((ref - start).total_seconds() / 3600.0, 0.0)


def get_order_detail(
    session: Session,
    *,
    order_id: int,
    sla_hours: float = 48.0,
    include_samples: bool = True,
    include_tests: bool = False,
) -> Optional[OrderDetailResponse]:
    if is_banned(session, "order", order_id):
        return None
    order = session.get(Order, order_id)
    if not order:
        return None
    if is_banned(session, "customer", order.customer_account_id):
        return None

    age_hours = _age_hours(order.date_created)
    pending_samples = session.execute(
        select(func.count()).where(Sample.order_id == order.id, Sample.completed_date.is_(None))
    ).scalar_one_or_none() or 0

    pending_tests = session.execute(
        select(func.count())
        .select_from(Test)
        .join(Sample, Sample.id == Test.sample_id)
        .where(Sample.order_id == order.id, Test.report_completed_date.is_(None))
    ).scalar_one_or_none() or 0

    order_payload = {
        "id": order.id,
        "custom_formatted_id": order.custom_formatted_id,
        "state": order.state,
        "sla_status": _classify_sla(age_hours, sla_hours),
        "sla_hours": sla_hours,
        "age_hours": round(age_hours, 2),
        "date_created": order.date_created,
        "date_completed": order.date_completed,
        "date_order_reported": order.date_order_reported,
        "date_received": order.date_received,
        "pending_samples": pending_samples,
        "pending_tests": pending_tests,
    }

    samples_payload: list[OrderSampleItem] | None = None
    if include_samples:
        sample_rows = [
            row
            for row in session.execute(
                select(Sample.id, Sample.sample_name, Sample.state, Sample.has_report)
                .where(Sample.order_id == order.id)
                .order_by(Sample.date_created.desc().nullslast())
            ).all()
            if not is_banned(session, "sample", row.id)
        ]
        sample_ids = [row.id for row in sample_rows]
        tests_map: dict[int, list[OrderSampleTestItem]] = {}
        pending_map: dict[int, int] = {}

        if sample_ids:
            pending_rows = session.execute(
                select(Sample.id, func.count().label("pending"))
                .join(Test, Test.sample_id == Sample.id)
                .where(Sample.id.in_(sample_ids), Test.report_completed_date.is_(None))
                .group_by(Sample.id)
            )
            pending_map = {row.id: int(row.pending) for row in pending_rows}

            if include_tests:
                tests_stmt = (
                    select(Test.id, Test.sample_id, Test.label_abbr, Test.state, Test.report_completed_date, Test.has_report)
                    .where(Test.sample_id.in_(sample_ids))
                    .order_by(Test.date_created.desc().nullslast())
                )
                for row in session.execute(tests_stmt):
                    if is_banned(session, "test", row.id):
                        continue
                    tests_map.setdefault(row.sample_id, []).append(
                        OrderSampleTestItem(
                            id=row.id,
                            label_abbr=row.label_abbr,
                            state=row.state,
                            has_report=row.has_report,
                            report_completed_date=row.report_completed_date,
                        )
                    )

        samples_payload = [
            OrderSampleItem(
                id=row.id,
                sample_name=row.sample_name,
                state=row.state,
                has_report=row.has_report,
                pending_tests=pending_map.get(row.id),
                tests=tests_map.get(row.id),
            )
            for row in sample_rows
        ]

    customer_payload = None
    if order.customer_account_id is not None:
        customer = session.get(Customer, order.customer_account_id)
        if customer:
            customer_payload = {
                "id": customer.id,
                "name": customer.name,
            }

    return OrderDetailResponse(
        order=order_payload,
        customer=customer_payload,
        samples=samples_payload,
    )


def get_sample_detail(
    session: Session,
    *,
    sample_id: int,
    sla_hours: Optional[float] = 48.0,
    include_tests: bool = True,
    include_batches: bool = True,
) -> Optional[SampleDetailResponse]:
    if is_banned(session, "sample", sample_id):
        return None
    sample = session.get(Sample, sample_id)
    if not sample:
        return None
    if is_banned(session, "order", sample.order_id):
        return None

    order = session.get(Order, sample.order_id)
    sla_value = sla_hours if sla_hours is not None else 48.0
    age_hours = _age_hours(sample.date_created)
    sample_payload = {
        "id": sample.id,
        "sample_name": sample.sample_name,
        "custom_formatted_id": sample.custom_formatted_id,
        "order_id": sample.order_id,
        "state": sample.state,
        "date_created": sample.date_created,
        "start_date": sample.start_date,
        "completed_date": sample.completed_date,
        "matrix_type": sample.matrix_type,
        "sla_status": _classify_sla(age_hours, sla_value),
        "sla_hours": sla_value,
    }

    tests_payload = None
    if include_tests:
        tests_payload = [
            SampleTestItem(
                id=test.id,
                label_abbr=test.label_abbr,
                state=test.state,
                has_report=test.has_report,
                report_completed_date=test.report_completed_date,
            )
            for test in session.scalars(select(Test).where(Test.sample_id == sample.id))
            if not is_banned(session, "test", test.id)
        ]

    batches_payload = None
    if include_batches and sample.batch_ids:
        batches_payload = [
            SampleBatchItem(id=bid, display_name=name)
            for bid, name in session.execute(select(Batch.id, Batch.display_name).where(Batch.id.in_(sample.batch_ids)))
            if not is_banned(session, "batch", bid)
        ]

    order_payload = None
    if order and not is_banned(session, "customer", order.customer_account_id):
        customer_info = None
        if order.customer_account_id:
            customer = session.get(Customer, order.customer_account_id)
            if customer:
                customer_info = {"id": customer.id, "name": customer.name}
        order_payload = {
            "id": order.id,
            "state": order.state,
            "customer": customer_info,
        }

    return SampleDetailResponse(
        sample=sample_payload,
        order=order_payload,
        tests=tests_payload,
        batches=batches_payload,
    )


def get_test_detail(
    session: Session,
    *,
    test_id: int,
    sla_hours: float = 48.0,
    include_sample: bool = True,
    include_order: bool = True,
    include_batches: bool = True,
) -> Optional[TestDetailResponse]:
    if is_banned(session, "test", test_id):
        return None
    test = session.get(Test, test_id)
    if not test:
        return None
    sample = session.get(Sample, test.sample_id) if include_sample or include_order else None
    if sample and is_banned(session, "sample", sample.id):
        return None
    order = session.get(Order, sample.order_id) if sample and include_order else None
    if order:
        if is_banned(session, "order", order.id):
            return None
        if order.customer_account_id and is_banned(session, "customer", order.customer_account_id):
            return None

    age_hours = _age_hours(test.date_created, test.report_completed_date)
    test_payload = {
        "id": test.id,
        "label_abbr": test.label_abbr,
        "state": test.state,
        "has_report": test.has_report,
        "date_created": test.date_created,
        "report_completed_date": test.report_completed_date,
        "sla_status": _classify_sla(age_hours, sla_hours),
        "sla_hours": sla_hours,
        "worksheet_raw": test.worksheet_raw,
    }

    sample_payload = None
    if sample and include_sample:
        sample_payload = {
            "id": sample.id,
            "sample_name": sample.sample_name,
            "state": sample.state,
        }

    order_payload = None
    if order and include_order:
        customer_info = None
        if order.customer_account_id:
            customer = session.get(Customer, order.customer_account_id)
            if customer:
                customer_info = {"id": customer.id, "name": customer.name}
        order_payload = {
            "id": order.id,
            "state": order.state,
            "customer": customer_info,
        }

    batches_payload = None
    if include_batches and test.batch_ids:
        batches_payload = [
            TestBatchItem(id=bid, display_name=name)
            for bid, name in session.execute(select(Batch.id, Batch.display_name).where(Batch.id.in_(test.batch_ids)))
        ]

    return TestDetailResponse(
        test=test_payload,
        sample=sample_payload,
        order=order_payload,
        batches=batches_payload,
    )
