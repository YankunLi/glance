"""add service uuid on images

Revision ID: board
Revises: abandon
Create Date: 2017-12-01 17:25:38.316923

"""

from alembic import op
from sqlalchemy import Column, String

# revision identifiers, used by Alembic.
revision = 'board'
down_revision = 'abandon'
branch_labels = None
depends_on = None


def _add_service_uuid_column():
    col = Column('service_uuid', String(36), nullable=False)
    op.add_column('images', col)

def _drop_service_uuid_column():
    op.drop_column('service_uuid', 'images')

def upgrade():
    _add_service_uuid_column()

def downgrade():
    _drop_service_uuid_column()
