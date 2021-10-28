"""
Functions for interacting with flow run ORM objects.
Intended for internal use by the Orion API.
"""

import contextlib
from typing import List
from uuid import UUID

import pendulum
import sqlalchemy as sa
from sqlalchemy import delete, select

from prefect.orion import models, schemas
from prefect.orion.orchestration.core_policy import CoreFlowPolicy
from prefect.orion.orchestration.global_policy import GlobalFlowPolicy
from prefect.orion.orchestration.rules import (
    FlowOrchestrationContext,
    OrchestrationResult,
)
from prefect.orion.database.dependencies import inject_db_config


@inject_db_config
async def create_flow_run(
    session: sa.orm.Session,
    flow_run: schemas.core.FlowRun,
    db_config=None,
):
    """Creates a new flow run.

    If the provided flow run has a state attached, it will also be created.

    Args:
        session: a database session
        flow_run: a flow run model

    Returns:
        db_config.FlowRun: the newly-created flow run
    """

    now = pendulum.now("UTC")
    # if there's no idempotency key, just create the run
    if not flow_run.idempotency_key:
        model = db_config.FlowRun(
            **flow_run.dict(
                shallow=True,
                exclude={
                    "state",
                    "estimated_run_time",
                    "estimated_start_time_delta",
                },
            ),
            state=None,
        )
        session.add(model)
        await session.flush()

    # otherwise let the database take care of enforcing idempotency
    else:
        insert_stmt = (
            (await db_config.insert(db_config.FlowRun))
            .values(
                **flow_run.dict(shallow=True, exclude={"state"}, exclude_unset=True)
            )
            .on_conflict_do_nothing(
                index_elements=db_config.flow_run_unique_upsert_columns,
            )
        )
        await session.execute(insert_stmt)
        query = (
            sa.select(db_config.FlowRun)
            .where(
                sa.and_(
                    db_config.FlowRun.flow_id == flow_run.flow_id,
                    db_config.FlowRun.idempotency_key == flow_run.idempotency_key,
                )
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
        result = await session.execute(query)
        model = result.scalar()

    if model.created >= now and flow_run.state:
        await models.flow_runs.set_flow_run_state(
            session=session,
            flow_run_id=model.id,
            state=flow_run.state,
            force=True,
        )
    return model


@inject_db_config
async def update_flow_run(
    session: sa.orm.Session,
    flow_run_id: UUID,
    flow_run: schemas.actions.FlowRunUpdate,
    db_config=None,
) -> bool:
    """
    Updates a flow run.

    Args:
        session: a database session
        flow_run_id: the flow run id to update
        flow_run: a flow run model

    Returns:
        bool: whether or not matching rows were found to update
    """

    if not isinstance(flow_run, schemas.actions.FlowRunUpdate):
        raise ValueError(
            f"Expected parameter flow_run to have type schemas.actions.FlowRunUpdate, got {type(flow_run)!r} instead"
        )

    update_stmt = (
        sa.update(db_config.FlowRun).where(db_config.FlowRun.id == flow_run_id)
        # exclude_unset=True allows us to only update values provided by
        # the user, ignoring any defaults on the model
        .values(**flow_run.dict(shallow=True, exclude_unset=True))
    )
    result = await session.execute(update_stmt)
    return result.rowcount > 0


@inject_db_config
async def read_flow_run(
    session: sa.orm.Session,
    flow_run_id: UUID,
    db_config=None,
):
    """
    Reads a flow run by id.

    Args:
        session: A database session
        flow_run_id: a flow run id

    Returns:
        db_config.FlowRun: the flow run
    """

    return await session.get(db_config.FlowRun, flow_run_id)


@inject_db_config
async def _apply_flow_run_filters(
    query,
    flow_filter: schemas.filters.FlowFilter = None,
    flow_run_filter: schemas.filters.FlowRunFilter = None,
    task_run_filter: schemas.filters.TaskRunFilter = None,
    deployment_filter: schemas.filters.DeploymentFilter = None,
    db_config=None,
):
    """
    Applies filters to a flow run query as a combination of EXISTS subqueries.
    """

    if flow_run_filter:
        query = query.where((await flow_run_filter.as_sql_filter()))

    if deployment_filter:
        exists_clause = select(db_config.Deployment).where(
            db_config.Deployment.id == db_config.FlowRun.deployment_id,
            (await deployment_filter.as_sql_filter()),
        )
        query = query.where(exists_clause.exists())

    if flow_filter or task_run_filter:

        if flow_filter:
            exists_clause = select(db_config.Flow).where(
                db_config.Flow.id == db_config.FlowRun.flow_id,
                (await flow_filter.as_sql_filter()),
            )

        if task_run_filter:
            if not flow_filter:
                exists_clause = select(db_config.TaskRun).where(
                    db_config.TaskRun.flow_run_id == db_config.FlowRun.id
                )
            else:
                exists_clause = exists_clause.join(
                    db_config.TaskRun,
                    db_config.TaskRun.flow_run_id == db_config.FlowRun.id,
                )
            exists_clause = exists_clause.where(
                db_config.FlowRun.id == db_config.TaskRun.flow_run_id,
                (await task_run_filter.as_sql_filter()),
            )

        query = query.where(exists_clause.exists())

    return query


@inject_db_config
async def read_flow_runs(
    session: sa.orm.Session,
    flow_filter: schemas.filters.FlowFilter = None,
    flow_run_filter: schemas.filters.FlowRunFilter = None,
    task_run_filter: schemas.filters.TaskRunFilter = None,
    deployment_filter: schemas.filters.DeploymentFilter = None,
    offset: int = None,
    limit: int = None,
    sort: schemas.sorting.FlowRunSort = schemas.sorting.FlowRunSort.ID_DESC,
    db_config=None,
):
    """
    Read flow runs.

    Args:
        session: a database session
        flow_filter: only select flow runs whose flows match these filters
        flow_run_filter: only select flow runs match these filters
        task_run_filter: only select flow runs whose task runs match these filters
        deployment_filter: only sleect flow runs whose deployments match these filters
        offset: Query offset
        limit: Query limit
        sort: Query sort

    Returns:
        List[db_config.FlowRun]: flow runs
    """

    query = select(db_config.FlowRun).order_by(await sort.as_sql_sort())

    query = await _apply_flow_run_filters(
        query,
        flow_filter=flow_filter,
        flow_run_filter=flow_run_filter,
        task_run_filter=task_run_filter,
        deployment_filter=deployment_filter,
        db_config=db_config,
    )

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    result = await session.execute(query)
    return result.scalars().unique().all()


@inject_db_config
async def count_flow_runs(
    session: sa.orm.Session,
    flow_filter: schemas.filters.FlowFilter = None,
    flow_run_filter: schemas.filters.FlowRunFilter = None,
    task_run_filter: schemas.filters.TaskRunFilter = None,
    deployment_filter: schemas.filters.DeploymentFilter = None,
    db_config=None,
) -> int:
    """
    Count flow runs.

    Args:
        session: a database session
        flow_filter: only count flow runs whose flows match these filters
        flow_run_filter: only count flow runs that match these filters
        task_run_filter: only count flow runs whose task runs match these filters
        deployment_filter: only count flow runs whose deployments match these filters

    Returns:
        int: count of flow runs
    """

    query = select(sa.func.count(sa.text("*"))).select_from(db_config.FlowRun)

    query = await _apply_flow_run_filters(
        query,
        flow_filter=flow_filter,
        flow_run_filter=flow_run_filter,
        task_run_filter=task_run_filter,
        deployment_filter=deployment_filter,
        db_config=db_config,
    )

    result = await session.execute(query)
    return result.scalar()


@inject_db_config
async def delete_flow_run(
    session: sa.orm.Session, flow_run_id: UUID, db_config=None
) -> bool:
    """
    Delete a flow run by flow_run_id.

    Args:
        session: A database session
        flow_run_id: a flow run id

    Returns:
        bool: whether or not the flow run was deleted
    """

    result = await session.execute(
        delete(db_config.FlowRun).where(db_config.FlowRun.id == flow_run_id)
    )
    return result.rowcount > 0


@inject_db_config
async def set_flow_run_state(
    session: sa.orm.Session,
    flow_run_id: UUID,
    state: schemas.states.State,
    force: bool = False,
    db_config=None,
):
    """
    Creates a new orchestrated flow run state.

    Setting a new state on a run is the one of the principal actions that is governed by
    Orion's orchestration logic. Setting a new run state will not guarantee creation,
    but instead trigger orchestration rules to govern the proposed `state` input. If
    the state is considered valid, it will be written to the database. Otherwise, a
    it's possible a different state, or no state, will be created. A `force` flag is
    supplied to bypass a subset of orchestration logic.

    Args:
        session: a database session
        flow_run_id: the flow run id
        state: a flow run state model
        force: if False, orchestration rules will be applied that may alter or prevent
            the state transition. If True, orchestration rules are not applied.

    Returns:
        OrchestrationResult object
    """

    # load the flow run
    run = await models.flow_runs.read_flow_run(
        session=session,
        flow_run_id=flow_run_id,
    )

    if not run:
        raise ValueError(f"Invalid flow run: {flow_run_id}")

    initial_state = run.state.as_state() if run.state else None
    initial_state_type = initial_state.type if initial_state else None
    proposed_state_type = state.type if state else None
    intended_transition = (initial_state_type, proposed_state_type)

    global_rules = GlobalFlowPolicy.compile_transition_rules(*intended_transition)

    if force:
        orchestration_rules = []
    else:
        orchestration_rules = CoreFlowPolicy.compile_transition_rules(
            *intended_transition
        )

    context = FlowOrchestrationContext(
        session=session,
        run=run,
        initial_state=initial_state,
        proposed_state=state,
    )

    # apply orchestration rules and create the new flow run state
    async with contextlib.AsyncExitStack() as stack:
        for rule in orchestration_rules:
            context = await stack.enter_async_context(
                rule(context, *intended_transition)
            )

        for rule in global_rules:
            context = await stack.enter_async_context(rule(context))

        await context.validate_proposed_state()

    await session.flush()

    result = OrchestrationResult(
        state=context.validated_state,
        status=context.response_status,
        details=context.response_details,
    )

    return result
