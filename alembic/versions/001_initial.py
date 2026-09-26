"""Initial schema."""

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from serah.models import Base

    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    from serah.models import Base

    Base.metadata.drop_all(op.get_bind())
