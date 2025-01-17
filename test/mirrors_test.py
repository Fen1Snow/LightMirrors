import unittest

from utils import call

PYPI_HOST = "pypi.local.homeinfra.org"
PYPI_INDEX = f"http://{PYPI_HOST}/simple"
TORCH_HOST = "torch.local.homeinfra.org"
TORCH_INDEX = f"http://{TORCH_HOST}/whl"


class TestPypi(unittest.TestCase):

    def test_pypi_http(self):
        call(f"pip download -i {PYPI_INDEX} django --trusted-host {PYPI_HOST}  --dest /tmp/pypi/")

    def test_torch_http(self):
        call(f"pip download -i {TORCH_INDEX} tqdm --trusted-host {TORCH_HOST} --dest /tmp/torch/")

    def test_docker_pull(self):
        call(f"docker pull docker.local.homeinfra.org/alpine:3.12")
