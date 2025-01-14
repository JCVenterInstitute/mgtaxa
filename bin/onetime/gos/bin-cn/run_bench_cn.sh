#!/bin/bash
set -ex

export BATCH_OPTIONS='-P 9223 -b n -l medium'
export MAKEFLOW_BATCH_QUEUE_TYPE=sge
export MAKEFLOW_MAX_REMOTE_JOBS=500

this_dir=$(dirname $0)

$MGT_HOME/bin/mgt_wrapper \
    makeflow -r 3 -S 30 -J 500 \
    $this_dir/bench_cn.mkf

