# CS5488 dedicated D4 cluster environment. Does not change system/Hadoop settings.
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PYSPARK_PYTHON=/home/lishuo/cs5488-round1/env/bin/python
export PYSPARK_DRIVER_PYTHON="$PYSPARK_PYTHON"
export SPARK_HOME=/home/lishuo/cs5488-round1/env/lib/python3.11/site-packages/pyspark
export CS5488_CLUSTER_HOME=/home/lishuo/cs5488-cluster
export SPARK_CONF_DIR="$CS5488_CLUSTER_HOME/conf"
export SPARK_LOG_DIR="$CS5488_CLUSTER_HOME/logs"
export SPARK_PID_DIR="$CS5488_CLUSTER_HOME/pids"
export SPARK_WORKER_DIR="$CS5488_CLUSTER_HOME/worker-work"
export SPARK_LOCAL_DIRS="$CS5488_CLUSTER_HOME/local"
export SPARK_IDENT_STRING=cs5488
export SPARK_DAEMON_MEMORY=512m
export SPARK_LOG_MAX_FILES=20
export SPARK_WORKER_CORES=2
export SPARK_WORKER_MEMORY=2g
export SPARK_HISTORY_OPTS='-Dspark.history.fs.logDirectory=file:///data/cs5488/event-logs -Dspark.history.ui.port=18080 -Dspark.history.fs.cleaner.enabled=false'
case "$(hostname -s)" in
  spark-master) export SPARK_LOCAL_IP=192.168.20.130 ;;
  spark-worker-1) export SPARK_LOCAL_IP=192.168.20.129 ;;
  spark-worker-2) export SPARK_LOCAL_IP=192.168.20.131 ;;
  *) echo 'Unknown CS5488 node' >&2; return 1 ;;
esac
export PATH="/home/lishuo/cs5488-round1/env/bin:$JAVA_HOME/bin:$SPARK_HOME/bin:$PATH"
