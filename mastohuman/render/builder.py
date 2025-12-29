import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlmodel import Session, select

from mastohuman.config.settings import settings
from mastohuman.db.models import Account, Status, Summary

logger = logging.getLogger(__name__)


class SiteBuilder:
    def __init__(self, session: Session):
        self.db = session
        self.output_dir = settings.output_dir
        self.env = Environment(
            loader=FileSystemLoader(settings.templates_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )
        # Add helpers
        self.env.globals["now"] = datetime.now(timezone.utc)
        self.env.filters["dateformat"] = lambda d: d.strftime("%Y-%m-%d %H:%M")

    def build(self, no_llm: bool = False):
        """Main build process."""
        self._prepare_output_dir()

        # Fetch Data
        # Get all accounts seen in the last 24h (or whatever the active window is)
        # For simplicity, we fetch all accounts that have been 'seen' recently.
        # A more robust query might be: join IngestRun or just use Account.last_seen_at

        # Sort by last_seen_at desc
        stmt = (
            select(Account, Summary)
            .outerjoin(Summary, Account.acct == Summary.account_acct)
            .order_by(Account.last_seen_at.desc())
        )
        results = self.db.exec(stmt).all()

        people_data = []
        for account, summary in results:
            # Skip accounts with no recent fetch or no activity if desired
            # Spec implies: list of people from the last daily pipeline

            # If no_llm is True, mock the summary
            if no_llm or not summary:
                s_obj = {
                    "headline": "No summary available",
                    "blurb": "Content processing pending or skipped.",
                    "tags": [],
                }
            else:
                import json

                tags = json.loads(summary.tags_json) if summary.tags_json else []
                s_obj = {
                    "headline": summary.headline,
                    "blurb": summary.blurb,
                    "tags": tags,
                }

            people_data.append(
                {
                    "account": account,
                    "summary": s_obj,
                    "slug": self._slugify(account.acct),
                }
            )

        # 1. Render Front Page
        self._render_template("index.html", "index.html", people=people_data)

        # 2. Render Person Pages
        for person in people_data:
            self._render_person_page(person)

        # 3. Copy Assets
        self._copy_assets()

        logger.info(f"Site built at: {self.output_dir.absolute()}")

    def _render_person_page(self, person):
        acct = person["account"].acct
        slug = person["slug"]

        # Fetch statuses: original only, no boosts, no replies
        stmt = (
            select(Status)
            .where(
                Status.account_acct == acct,
                Status.is_boost == False,
                Status.is_reply == False,
            )
            .order_by(Status.created_at.desc())
            .limit(settings.max_profile_statuses)
        )

        statuses = self.db.exec(stmt).all()

        out_path = Path(f"people/{slug}/index.html")
        self._render_template("person.html", out_path, person=person, statuses=statuses)

    def _render_template(self, template_name, output_rel_path, **kwargs):
        template = self.env.get_template(template_name)
        content = template.render(site_title=settings.site_title, **kwargs)

        dest = self.output_dir / output_rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)

    def _prepare_output_dir(self):
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True)
        # We don't wipe it clean to preserve existing assets if manual,
        # but spec says "overwrite in place".

    def _copy_assets(self):
        # Assume a static folder in templates or root
        # For now, we write a simple CSS file if it doesn't exist
        css_dir = self.output_dir / "assets"
        css_dir.mkdir(exist_ok=True)

        # (Optional: Copy actual static files from source)

    def archive_run(self):
        """Copy output_dir to archive_dir/timestamp."""
        if not settings.archive_dir:
            return

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = settings.archive_dir / ts
        shutil.copytree(self.output_dir, dest)
        logger.info(f"Archived run to {dest}")

    def _slugify(self, text):
        return text.replace("@", "_").replace(".", "_")
