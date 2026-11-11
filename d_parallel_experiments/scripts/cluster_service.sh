#!/usr/bin/env bash
set -euo pipefail
source /home/lishuo/cs5488-cluster/conf/spark-env.sh
action=${1:-check}
node=$(hostname -s)
daemon="$SPARK_HOME/sbin/spark-daemon.sh"
case "$action" in
  check)
    test -x "$JAVA_HOME/bin/java"
    test -x "$PYSPARK_PYTHON"
    test -f "$daemon"
    ip -4 -o addr show | grep -Fq " $SPARK_LOCAL_IP/"
    test "$(cat /data/cs5488/checks/master-ready.txt)" = cs5488-master-storage-v1
    if test "$node" != spark-master; then
      test "$(findmnt -n -o SOURCE --target /data/cs5488)" = '192.168.20.130:/data/cs5488'
    fi
    test -w /data/cs5488/event-logs
    "$PYSPARK_PYTHON" -c 'import sys,pyspark,pyarrow; assert sys.version_info[:2] == (3,11); assert pyspark.__version__ == "3.5.7"; print("Python",sys.version.split()[0],"Spark",pyspark.__version__,"PyArrow",pyarrow.__version__)'
    echo "CHECK_OK $node $SPARK_LOCAL_IP (no services launched)"
    ;;
  start)
    "$0" check
    if test "$node" = spark-master; then
      bash "$daemon" start org.apache.spark.deploy.master.Master 1 --host "$SPARK_LOCAL_IP" --port 7077 --webui-port 8080
      bash "$daemon" start org.apache.spark.deploy.history.HistoryServer 1
    else
      bash "$daemon" start org.apache.spark.deploy.worker.Worker 1 --host "$SPARK_LOCAL_IP" --port 7078 --webui-port 8081 --cores 2 --memory 2g --work-dir "$SPARK_WORKER_DIR" spark://192.168.20.130:7077
    fi
    ;;
  stop)
    if test "$node" = spark-master; then
      bash "$daemon" stop org.apache.spark.deploy.history.HistoryServer 1
      bash "$daemon" stop org.apache.spark.deploy.master.Master 1
    else
      bash "$daemon" stop org.apache.spark.deploy.worker.Worker 1
    fi
    ;;
  status)
    if test "$node" = spark-master; then
      bash "$daemon" status org.apache.spark.deploy.master.Master 1
      bash "$daemon" status org.apache.spark.deploy.history.HistoryServer 1
    else
      bash "$daemon" status org.apache.spark.deploy.worker.Worker 1
    fi
    ;;
  *) echo 'Usage: cluster_service.sh {check|start|status|stop}'; exit 2 ;;
esac
