import os

import pytest
from sklearn import datasets
import sklearn.neighbors as knn

import mlflow.sklearn
import mlflow.utils.model_utils as mlflow_model_utils
from mlflow.exceptions import MlflowException
from mlflow.models import Model
from mlflow.protos.databricks_pb2 import ErrorCode, RESOURCE_DOES_NOT_EXIST
from mlflow.mleap import FLAVOR_NAME as MLEAP_FLAVOR_NAME
from mlflow.utils.file_utils import TempDir


@pytest.fixture(scope="module")
def sklearn_knn_model():
    iris = datasets.load_iris()
    X = iris.data[:, :2]  # we only take the first two features.
    y = iris.target
    knn_model = knn.KNeighborsClassifier()
    knn_model.fit(X, y)
    return knn_model


@pytest.fixture
def model_path(tmpdir):
    return os.path.join(str(tmpdir), "model")


def test_get_flavor_configuration_throws_exception_when_model_configuration_does_not_exist(
    model_path,
):
    with pytest.raises(
        MlflowException, match='Could not find an "MLmodel" configuration file'
    ) as exc:
        mlflow_model_utils._get_flavor_configuration(
            model_path=model_path, flavor_name=mlflow.mleap.FLAVOR_NAME
        )
    assert exc.value.error_code == ErrorCode.Name(RESOURCE_DOES_NOT_EXIST)


def test_get_flavor_configuration_throws_exception_when_requested_flavor_is_missing(
    model_path, sklearn_knn_model
):
    mlflow.sklearn.save_model(sk_model=sklearn_knn_model, path=model_path)

    # The saved model contains the "sklearn" flavor, so this call should succeed
    sklearn_flavor_config = mlflow_model_utils._get_flavor_configuration(
        model_path=model_path, flavor_name=mlflow.sklearn.FLAVOR_NAME
    )
    assert sklearn_flavor_config is not None

    # The saved model does not contain the "mleap" flavor, so this call should fail
    with pytest.raises(MlflowException, match='Model does not have the "mleap" flavor') as exc:
        mlflow_model_utils._get_flavor_configuration(
            model_path=model_path, flavor_name=MLEAP_FLAVOR_NAME
        )
    assert exc.value.error_code == ErrorCode.Name(RESOURCE_DOES_NOT_EXIST)


def test_get_flavor_configuration_with_present_flavor_returns_expected_configuration(
    sklearn_knn_model, model_path
):
    mlflow.sklearn.save_model(sk_model=sklearn_knn_model, path=model_path)

    sklearn_flavor_config = mlflow_model_utils._get_flavor_configuration(
        model_path=model_path, flavor_name=mlflow.sklearn.FLAVOR_NAME
    )
    model_config = Model.load(os.path.join(model_path, "MLmodel"))
    assert sklearn_flavor_config == model_config.flavors[mlflow.sklearn.FLAVOR_NAME]


def test_add_code_to_system_path(sklearn_knn_model, model_path):
    mlflow.sklearn.save_model(
        sk_model=sklearn_knn_model,
        path=model_path,
        code_paths=[
            "tests/utils/test_resources/dummy_module.py",
            "tests/utils/test_resources/dummy_package",
        ],
    )

    sklearn_flavor_config = mlflow_model_utils._get_flavor_configuration(
        model_path=model_path, flavor_name=mlflow.sklearn.FLAVOR_NAME
    )
    with TempDir(chdr=True):
        # Load the model from a new directory that is not a parent of the source code path to
        # verify that source code paths and their subdirectories are resolved correctly
        with pytest.raises(ModuleNotFoundError, match="No module named 'dummy_module'"):
            import dummy_module

        mlflow_model_utils._add_code_from_conf_to_system_path(model_path, sklearn_flavor_config)
        import dummy_module

    # If this raises an exception it's because dummy_package.test imported
    # dummy_package.operator and not the built-in operator module. This only
    # happens if MLflow is misconfiguring the system path.
    from dummy_package import base  # pylint: disable=unused-import
