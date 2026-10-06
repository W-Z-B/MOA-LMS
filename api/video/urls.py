from video.api import urlpatterns as video_urls
from video.offline import urlpatterns as offline_urls

urlpatterns = [*video_urls, *offline_urls]
