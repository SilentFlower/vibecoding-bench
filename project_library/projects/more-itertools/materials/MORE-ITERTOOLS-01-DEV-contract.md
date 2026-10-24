# 流式清洗的转换异常通过一次性旁路回调报告

路线16：map_except/filter_except新增on_error旁路，逐个已消费坏行报告索引/原项/真实异常；falsey回调有效、回调与非列异常不吞，不缓存无限错误。
