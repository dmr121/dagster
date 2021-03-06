import json
import os
from difflib import SequenceMatcher

import pytest
import yaml
from click.testing import CliRunner

from dagster import seven
from dagster.cli.pipeline import pipeline_execute_command
from dagster.core.definitions.reconstructable import EPHEMERAL_NAME
from dagster.core.instance import DagsterInstance
from dagster.core.telemetry import REPO_STATS_ACTION, get_dir_from_dagster_home, hash_name
from dagster.core.test_utils import environ
from dagster.utils import file_relative_path, pushd, script_relative_path

EXPECTED_KEYS = set(
    [
        'action',
        'client_time',
        'elapsed_time',
        'event_id',
        'instance_id',
        'pipeline_name_hash',
        'num_pipelines_in_repo',
        'repo_hash',
        'metadata',
        'version',
    ]
)


def path_to_tutorial_file(path):
    return script_relative_path(
        os.path.join('../../../../examples/dagster_examples/intro_tutorial/', path)
    )


@pytest.mark.skipif(
    os.name == 'nt', reason="TemporaryDirectory disabled for win because of event.log contention"
)
def test_dagster_telemetry_enabled(caplog):
    with seven.TemporaryDirectory() as temp_dir:
        with environ({'DAGSTER_HOME': temp_dir}):
            with open(os.path.join(temp_dir, 'dagster.yaml'), 'w') as fd:
                yaml.dump({'telemetry': {'enabled': True}}, fd, default_flow_style=False)

            DagsterInstance.local_temp(temp_dir)
            runner = CliRunner(env={'DAGSTER_HOME': temp_dir})
            with pushd(path_to_tutorial_file('')):
                pipeline_name = 'hello_cereal_pipeline'
                result = runner.invoke(
                    pipeline_execute_command,
                    ['-f', path_to_tutorial_file('hello_cereal.py'), '-n', pipeline_name],
                )

                for record in caplog.records:
                    message = json.loads(record.getMessage())
                    if message.get('action') == REPO_STATS_ACTION:
                        assert message.get('pipeline_name_hash') == hash_name(
                            'hello_cereal_pipeline'
                        )
                        assert message.get('num_pipelines_in_repo') == str(1)
                        assert message.get('repo_hash') == hash_name(EPHEMERAL_NAME)
                    assert set(message.keys()) == EXPECTED_KEYS
                assert len(caplog.records) == 5
                assert result.exit_code == 0


@pytest.mark.skipif(
    os.name == 'nt', reason="TemporaryDirectory disabled for win because of event.log contention"
)
def test_dagster_telemetry_disabled(caplog):
    with seven.TemporaryDirectory() as temp_dir:
        with environ({'DAGSTER_HOME': temp_dir}):
            with open(os.path.join(temp_dir, 'dagster.yaml'), 'w') as fd:
                yaml.dump({'telemetry': {'enabled': False}}, fd, default_flow_style=False)

            DagsterInstance.local_temp(temp_dir)

            runner = CliRunner(env={'DAGSTER_HOME': temp_dir})
            with pushd(path_to_tutorial_file('')):
                pipeline_name = 'hello_cereal_pipeline'
                result = runner.invoke(
                    pipeline_execute_command,
                    ['-f', path_to_tutorial_file('hello_cereal.py'), '-n', pipeline_name],
                )

            assert not os.path.exists(os.path.join(get_dir_from_dagster_home('logs'), 'event.log'))
            assert len(caplog.records) == 0
            assert result.exit_code == 0


@pytest.mark.skipif(
    os.name == 'nt', reason="TemporaryDirectory disabled for win because of event.log contention"
)
def test_dagster_telemetry_unset(caplog):
    with seven.TemporaryDirectory() as temp_dir:
        with environ({'DAGSTER_HOME': temp_dir}):
            with open(os.path.join(temp_dir, 'dagster.yaml'), 'w') as fd:
                yaml.dump({}, fd, default_flow_style=False)

            DagsterInstance.local_temp(temp_dir)
            runner = CliRunner(env={'DAGSTER_HOME': temp_dir})
            with pushd(path_to_tutorial_file('')):
                pipeline_name = 'hello_cereal_pipeline'
                result = runner.invoke(
                    pipeline_execute_command,
                    ['-f', path_to_tutorial_file('hello_cereal.py'), '-n', pipeline_name],
                )

                for record in caplog.records:
                    message = json.loads(record.getMessage())
                    if message.get('action') == REPO_STATS_ACTION:
                        assert message.get('pipeline_name_hash') == hash_name(pipeline_name)
                        assert message.get('num_pipelines_in_repo') == str(1)
                        assert message.get('repo_hash') == hash_name(EPHEMERAL_NAME)
                    assert set(message.keys()) == EXPECTED_KEYS

                assert len(caplog.records) == 5
                assert result.exit_code == 0


@pytest.mark.skipif(
    os.name == 'nt', reason="TemporaryDirectory disabled for win because of event.log contention"
)
def test_repo_stats(caplog):
    with seven.TemporaryDirectory() as temp_dir:
        with environ({'DAGSTER_HOME': temp_dir}):
            with open(os.path.join(temp_dir, 'dagster.yaml'), 'w') as fd:
                yaml.dump({}, fd, default_flow_style=False)

            DagsterInstance.local_temp(temp_dir)
            runner = CliRunner(env={'DAGSTER_HOME': temp_dir})
            with pushd(path_to_tutorial_file('')):
                pipeline_name = 'multi_mode_with_resources'
                result = runner.invoke(
                    pipeline_execute_command,
                    [
                        '-y',
                        file_relative_path(__file__, '../repository.yaml'),
                        '-p',
                        'add',
                        '--tags',
                        '{ "foo": "bar" }',
                        pipeline_name,
                    ],
                )

                for record in caplog.records:
                    message = json.loads(record.getMessage())
                    if message.get('action') == REPO_STATS_ACTION:
                        assert message.get('pipeline_name_hash') == hash_name(pipeline_name)
                        assert message.get('num_pipelines_in_repo') == str(4)
                        assert message.get('repo_hash') == hash_name('dagster_test_repository')
                    assert set(message.keys()) == EXPECTED_KEYS

                assert len(caplog.records) == 5
                assert result.exit_code == 0


# Sanity check that the hash function maps these similar names to sufficiently dissimilar strings
# From the docs, SequenceMatcher `does not yield minimal edit sequences, but does tend to yield
# matches that "look right" to people. As a rule of thumb, a .ratio() value over 0.6 means the
# sequences are close matches`
# Other than above, 0.4 was picked arbitrarily.
def test_hash_name():
    pipelines = ['pipeline_1', 'pipeline_2', 'pipeline_3']
    hashes = [hash_name(p) for p in pipelines]
    for h in hashes:
        assert len(h) == 64

    assert SequenceMatcher(None, hashes[0], hashes[1]).ratio() < 0.4
    assert SequenceMatcher(None, hashes[0], hashes[2]).ratio() < 0.4
    assert SequenceMatcher(None, hashes[1], hashes[2]).ratio() < 0.4
