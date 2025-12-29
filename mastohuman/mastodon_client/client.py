import logging
from typing import Any, Callable, Generator

from mastodon import Mastodon, MastodonNetworkError, MastodonRatelimitError

from mastohuman.config.settings import settings

# Remove tenacity; Mastodon.py handles retries/waiting nicely with ratelimit_method='wait'


logger = logging.getLogger(__name__)


class MastodonClient:
    def __init__(self):
        self.api = Mastodon(
            api_base_url=settings.mastodon_base_url,
            access_token=settings.mastodon_access_token.get_secret_value(),
            user_agent=settings.mastodon_user_agent,
            request_timeout=settings.mastodon_timeout_s,
            ratelimit_method="wait",  # Handles 429s automatically by sleeping
        )

    def get_me(self) -> dict:
        return self.api.account_verify_credentials()

    def get_account_following(self, account_id: str | int, limit: int = 40) -> Any:
        """Fetch accounts followed by the specified user."""
        return self.api.account_following(account_id, limit=limit)

    def get_home_timeline(self, limit: int = 40) -> Any:
        return self.api.timeline_home(limit=limit)

    def get_account_statuses(self, account_id: str | int, limit: int = 40) -> Any:
        return self.api.account_statuses(
            account_id, limit=limit, exclude_reblogs=True, exclude_replies=False
        )

    def paginate(
        self, initial_fetch_func: Callable, **kwargs
    ) -> Generator[list[dict], None, None]:
        """
        Adapts Mastodon.py pagination to a generator.
        """
        try:
            page = initial_fetch_func(**kwargs)
        except (MastodonNetworkError, MastodonRatelimitError) as e:
            logger.error(f"Network error on initial fetch: {e}")
            return

        while page:
            yield page
            try:
                page = self.api.fetch_next(page)
            except (MastodonNetworkError, MastodonRatelimitError) as e:
                logger.error(f"Network error during pagination: {e}")
                break

            if not page:
                break
