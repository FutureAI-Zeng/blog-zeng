---
title: Java 并发编程笔记：线程池的正确姿势
description: 总结 Java 线程池的核心参数与常见踩坑，避免线上 OOM 与任务堆积。
pubDate: 2025-11-02
category: 技术
tags: ["Java", "后端"]
---

# Java 并发编程笔记

线程池是后端开发的高频考点，也是事故高发区。

## 核心参数

- `corePoolSize`：核心线程数
- `maximumPoolSize`：最大线程数
- `workQueue`：任务队列
- `RejectedExecutionHandler`：拒绝策略

## 常见坑

1. 用 `Executors.newFixedThreadPool` 容易因无界队列堆积任务导致 OOM。
2. 拒绝策略选错，重要任务被静默丢弃。

> 生产环境建议手动 `new ThreadPoolExecutor(...)`，明确队列容量与拒绝策略。
