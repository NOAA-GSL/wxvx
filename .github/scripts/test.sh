. $(dirname ${BASH_SOURCE[0]})/common.sh

run_tests() {
  set -x
  make test
}

ci_conda_activate
CONDEV_SHELL_CMD=run_tests condev-shell
