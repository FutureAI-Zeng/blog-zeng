---
title: 大数据学习路线梳理
description: 从 Hadoop 到 Flink，整理一条相对完整的大数据技术学习路径，供入门参考。
pubDate: 2026-09-10
category: 技术
tags: ["大数据"]
---

# 大数据学习路线

大数据体系庞大，这里梳理一条主线，避免一开始就被铺天盖地的组件劝退。

## 存储与计算

- **HDFS**：分布式文件存储的基石
- **MapReduce / Spark**：批处理计算
- **Flink**：流式计算

## 调度与治理

- **YARN / Kubernetes**：资源调度
- **Hive / Iceberg**：数据仓库与表格式

## 建议

先把 **Spark + HDFS** 跑通一个端到端案例，再补流式和治理，事半功倍。
