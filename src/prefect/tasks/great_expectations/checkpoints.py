"""
Great Expectations checkpoints are combinations of data source, expectation suite, and
validation operators configuration that can be used to run Great Expectations actions.
Checkpoints are the preferred deployment of validation configuration; you can read more about
setting up checkpoints [at the Great Expectation
docs](https://docs.greatexpectations.io/en/latest/tutorials/getting_started/set_up_your_first_checkpoint.html#set-up-your-first-checkpoint).

You can use these task library tasks to interact with your Great Expectations checkpoint from a
Prefect flow.
"""
from typing import Optional

import great_expectations as ge
from great_expectations.checkpoint import Checkpoint
from packaging import version

import prefect
from prefect import Task
from prefect.backend.artifacts import create_markdown_artifact
from prefect.engine import signals
from prefect.utilities.tasks import defaults_from_attrs


class RunGreatExpectationsValidation(Task):
    """
    Task for running data validation with Great Expectations.
    Works with both the Great Expectations v2 (batch_kwargs) and v3 (Batch Request) APIs.

    Example using the GE getting started tutorial:
    https://github.com/superconductive/ge_tutorials/tree/main/getting_started_tutorial_final_v3_api

    The task can be used to run validation in one of the following ways:

    1. checkpoint_name: the name of a pre-configured checkpoint (which bundles expectation suites
    and batch_kwargs). This is the preferred option.
    2. expectation_suite AND batch_kwargs, where batch_kwargs is a dict. This will only work with the
    Great Expectations v2 API.
    3. assets_to_validate: a list of dicts of expectation_suite + batch_kwargs. This will only work
    with the Great Expectations v2 API.

    To create a checkpoint you can use:
    - for the v2 API: `great_expectations checkpoint new <expectations_suite_name> <checkpoint_name>`
    - for the v3 API: `great_expectations --v3-api checkpoint new <checkpoint_name>`

    Here is an example that can be used with both v2 and v3 API provided that
    the checkpoint has been already created, as described above:
    ```python
    from prefect import Flow, Parameter
    from prefect.tasks.great_expectations import RunGreatExpectationsValidation

    validation_task = RunGreatExpectationsValidation()

    with Flow("ge_test") as flow:
        checkpoint_name = Parameter("checkpoint_name")
        prev_run_row_count = 100  # can be taken eg. from Prefect KV store
        validation_task(
            checkpoint_name=checkpoint_name,
            evaluation_parameters=dict(prev_run_row_count=prev_run_row_count),
        )

    flow.run(parameters={"checkpoint_name": "my_checkpoint"})
    ```


    Args:
        - checkpoint_name (str, optional): the name of a pre-configured checkpoint; should match the
            filename of the checkpoint without the extension. Either checkpoint_name or checkpoint
            is required when using the Great Expectations v3 API.
        - ge_checkpoint (Checkpoint, optional): an in-memory GE `Checkpoint` object used to perform
            validation. If not provided then `checkpoint_name` will be used to load the specified
            checkpoint. Either checkpoint_name or checkpoint is required when using the Great
            Expectations v3 API.
        - checkpoint_kwargs (Dict, optional): A dictionary whose keys match the parameters of
            `CheckpointConfig` which can be used to update and populate the task's Checkpoint at runtime.
            Only used in the Great Expectations v3 API.
        - context (DataContext, optional): an in-memory GE DataContext object. e.g.
            `ge.data_context.DataContext()` If not provided then `context_root_dir` will be used to
            look for one.
        - assets_to_validate (list, optional): A list of assets to validate when running the
            validation operator. Only used in the Great Expectations v2 API
        - batch_kwargs (dict, optional): a dictionary of batch kwargs to be used when validating
            assets. Only used in the Great Expectations v2 API
        - expectation_suite_name (str, optional): the name of an expectation suite to be used when
            validating assets. Only used in the Great Expectations v2 API
        - context_root_dir (str, optional): the absolute or relative path to the directory holding
            your `great_expectations.yml`
        - runtime_environment (dict, optional): a dictionary of great expectation config key-value
            pairs to overwrite your config in `great_expectations.yml`
        - run_name (str, optional): the name of this  Great Expectation validation run; defaults to
            the task slug
        - run_info_at_end (bool, optional): add run info to the end of the artifact generated by this
            task. Defaults to `True`.
        - disable_markdown_artifact (bool, optional): toggle the posting of a markdown artifact from
            this tasks. Defaults to `False`.
        - validation_operator (str, optional): configure the actions to be executed after running
            validation. Defaults to `action_list_operator`
        - evaluation_parameters (Optional[dict], optional): the evaluation parameters to use when
            running validation. For more information, see
            [example](https://docs.prefect.io/api/latest/tasks/great_expectations.html#rungreatexpectationsvalidation)
            and
            [docs](https://docs.greatexpectations.io/en/latest/reference/core_concepts/evaluation_parameters.html).
        - **kwargs (dict, optional): additional keyword arguments to pass to the Task constructor
    """

    def __init__(
        self,
        checkpoint_name: str = None,
        ge_checkpoint: Checkpoint = None,
        checkpoint_kwargs: dict = None,
        context: ge.DataContext = None,
        assets_to_validate: list = None,
        batch_kwargs: dict = None,
        expectation_suite_name: str = None,
        context_root_dir: str = None,
        runtime_environment: Optional[dict] = None,
        run_name: str = None,
        run_info_at_end: bool = True,
        disable_markdown_artifact: bool = False,
        validation_operator: str = "action_list_operator",
        evaluation_parameters: Optional[dict] = None,
        **kwargs,
    ):
        self.checkpoint_name = checkpoint_name
        self.ge_checkpoint = ge_checkpoint
        self.checkpoint_kwargs = checkpoint_kwargs
        self.context = context
        self.assets_to_validate = assets_to_validate
        self.batch_kwargs = batch_kwargs
        self.expectation_suite_name = expectation_suite_name
        self.context_root_dir = context_root_dir
        self.runtime_environment = runtime_environment or dict()
        self.run_name = run_name
        self.run_info_at_end = run_info_at_end
        self.disable_markdown_artifact = disable_markdown_artifact
        self.validation_operator = validation_operator
        self.evaluation_parameters = evaluation_parameters

        super().__init__(**kwargs)

    @defaults_from_attrs(
        "checkpoint_name",
        "ge_checkpoint",
        "checkpoint_kwargs",
        "context",
        "assets_to_validate",
        "batch_kwargs",
        "expectation_suite_name",
        "context_root_dir",
        "runtime_environment",
        "run_name",
        "run_info_at_end",
        "disable_markdown_artifact",
        "validation_operator",
        "evaluation_parameters",
    )
    def run(
        self,
        checkpoint_name: str = None,
        ge_checkpoint: Checkpoint = None,
        checkpoint_kwargs: dict = None,
        context: ge.DataContext = None,
        assets_to_validate: list = None,
        batch_kwargs: dict = None,
        expectation_suite_name: str = None,
        context_root_dir: str = None,
        runtime_environment: Optional[dict] = None,
        run_name: str = None,
        run_info_at_end: bool = True,
        disable_markdown_artifact: bool = False,
        validation_operator: str = "action_list_operator",
        evaluation_parameters: Optional[dict] = None,
    ):
        """
        Task run method.

        Args:
            - checkpoint_name (str, optional): the name of a pre-configured checkpoint; should match the
                filename of the checkpoint without the extension. Either checkpoint_name or
                checkpoint_config is required when using the Great Expectations v3 API.
            - ge_checkpoint (Checkpoint, optional): an in-memory GE `Checkpoint` object used to perform
                validation. If not provided then `checkpoint_name` will be used to load the specified
                checkpoint.
            - checkpoint_kwargs (Dict, optional): A dictionary whose keys match the parameters of
                `CheckpointConfig` which can be used to update and populate the task's Checkpoint at
                runtime.
            - context (DataContext, optional): an in-memory GE `DataContext` object. e.g.
                `ge.data_context.DataContext()` If not provided then `context_root_dir` will be used to
                look for one.
            - assets_to_validate (list, optional): A list of assets to validate when running the
                validation operator. Only used in the Great Expectations v2 API
            - batch_kwargs (dict, optional): a dictionary of batch kwargs to be used when validating
                assets. Only used in the Great Expectations v2 API
            - expectation_suite_name (str, optional): the name of an expectation suite to be used when
                validating assets. Only used in the Great Expectations v2 API
            - context_root_dir (str, optional): the absolute or relative path to the directory holding
                your `great_expectations.yml`
            - runtime_environment (dict, optional): a dictionary of great expectation config key-value
                pairs to overwrite your config in `great_expectations.yml`
            - run_name (str, optional): the name of this  Great Expectation validation run; defaults to
                the task slug
            - run_info_at_end (bool, optional): add run info to the end of the artifact generated by this
                task. Defaults to `True`.
            - disable_markdown_artifact (bool, optional): toggle the posting of a markdown artifact from
                this tasks. Defaults to `False`.
            - evaluation_parameters (Optional[dict], optional): the evaluation parameters to use when
                running validation. For more information, see
                [example](https://docs.prefect.io/api/latest/tasks/great_expectations.html#rungreatexpectationsvalidation)
                and
                [docs](https://docs.greatexpectations.io/en/latest/reference/core_concepts/evaluation_parameters.html).
            - validation_operator (str, optional): configure the actions to be executed after running
                validation. Defaults to `action_list_operator`.

        Raises:
            - 'signals.FAIL' if the validation was not a success

        Returns:
            - result
                ('great_expectations.validation_operators.types.validation_operator_result.ValidationOperatorResult'):
                The Great Expectations metadata returned from the validation if the v2 (batch_kwargs) API
                is used.

                ('great_expectations.checkpoint.checkpoint.CheckpointResult'):
                The Great Expectations metadata returned from running the provided checkpoint if a
                checkpoint name is provided.

        """

        if version.parse(ge.__version__) < version.parse("0.13.8"):
            self.logger.warn(
                f"You are using great_expectations version {ge.__version__} which may cause"
                "errors in this task. Please upgrade great_expections to 0.13.8 or later."
            )

        runtime_environment = runtime_environment or dict()
        checkpoint_kwargs = checkpoint_kwargs or dict()

        # Load context if not provided directly
        if not context:
            context = ge.DataContext(
                context_root_dir=context_root_dir,
                runtime_environment=runtime_environment,
            )

        # Check that the parameters are mutually exclusive
        if (
            sum(
                bool(x)
                for x in [
                    (expectation_suite_name and batch_kwargs),
                    assets_to_validate,
                    checkpoint_name,
                    ge_checkpoint,
                ]
            )
            != 1
        ):
            raise ValueError(
                "Exactly one of expectation_suite_name + batch_kwargs, assets_to_validate, "
                "checkpoint_name, or ge_checkpoint is required to run validation."
            )

        results = None
        # If there is a checkpoint or checkpoint name provided, run the checkpoint.
        # Checkpoints are the preferred deployment of validation configuration.
        if ge_checkpoint or checkpoint_name:
            ge_checkpoint = ge_checkpoint or context.get_checkpoint(checkpoint_name)
            results = ge_checkpoint.run(
                evaluation_parameters=evaluation_parameters,
                run_id={"run_name": run_name or prefect.context.get("task_slug")},
                **checkpoint_kwargs,
            )
        else:
            # If assets are not provided directly through `assets_to_validate` then they need be loaded
            #   get batch from `batch_kwargs` and `expectation_suite_name`
            if not assets_to_validate:
                assets_to_validate = [
                    context.get_batch(batch_kwargs, expectation_suite_name)
                ]

            # Run validation operator
            results = context.run_validation_operator(
                validation_operator,
                assets_to_validate=assets_to_validate,
                run_id={"run_name": run_name or prefect.context.get("task_slug")},
                evaluation_parameters=evaluation_parameters,
            )

        # Generate artifact markdown
        if not disable_markdown_artifact:
            validation_results_page_renderer = (
                ge.render.renderer.ValidationResultsPageRenderer(
                    run_info_at_end=run_info_at_end
                )
            )
            rendered_content_list = validation_results_page_renderer.render_validation_operator_result(
                # This also works with a CheckpointResult because of duck typing.
                # The passed in object needs a list_validation_results method that
                # returns a list of ExpectationSuiteValidationResult.
                validation_operator_result=results
            )
            markdown_artifact = " ".join(
                ge.render.view.DefaultMarkdownPageView().render(rendered_content_list)
            )

            create_markdown_artifact(markdown_artifact)

        if results.success is False:
            raise signals.FAIL(result=results)

        return results
