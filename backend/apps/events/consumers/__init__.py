from .cache_invalidation import CacheInvalidationConsumer
from .event_log import EventLogConsumer
from .notifications import NotificationsConsumer
from .order_live import OrderLiveConsumer
from .product_stats import ProductStatsConsumer

# name -> class; run_consumers starts one thread per entry
CONSUMERS = {c.name: c for c in (
    ProductStatsConsumer, CacheInvalidationConsumer, NotificationsConsumer, OrderLiveConsumer,
    EventLogConsumer,
)}
