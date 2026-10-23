from .cache_invalidation import CacheInvalidationConsumer
from .product_stats import ProductStatsConsumer

# name -> class; run_consumers starts one thread per entry
CONSUMERS = {c.name: c for c in (ProductStatsConsumer, CacheInvalidationConsumer)}
