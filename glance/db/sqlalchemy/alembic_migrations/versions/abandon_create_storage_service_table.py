"""create storage service table

Revision ID: abandon
Revises: pike01
Create Date: 2017-12-01 17:10:19.354867

"""

# revision identifiers, used by Alembic.
revision = 'abandon'
down_revision = 'pike01'
branch_labels = None
depends_on = None


from alembic import op
from sqlalchemy.schema import (
        Column, PrimaryKeyConstraint, ForeignKeyConstraint)

from glance.db.sqlalchemy.migrate_repo.schema import (
        Boolean, DateTime, String, BigInteger, Text)
from glance.db.sqlalchemy.models import JSONEncodedDict


def _add_storage_services_table():
    op.create_table('storage_services',
                    Column('id', String(36), nullable=False),
                    Column('name', String(30), nullable=True),
                    Column('schema', String(10), nullable=False),
                    Column('port', String(10), nullable=False),
                    Column('host', String(30), nullable=False),
                    Column('endpoint', String(100), nullable=False),
                    Column('status', String(30), nullable=False),
                    Column('total_size', BigInteger(), nullable=False),
                    Column('avail_size', BigInteger(), nullable=False),
                    Column('disk_wwn', String(50), nullable=False),
                    Column('file_system_uuid', String(50), nullable=False),
                    Column('storage_dir', String(100), nullable=False),
                    Column('created_at', DateTime(), nullable=False),
                    Column('updated_at', DateTime()),
                    Column('deleted_at', DateTime()),
                    Column('deleted', Boolean(), nullable=False, default=False),
                    PrimaryKeyConstraint('id'),
                    mysql_engine='InnoDB',
                    mysql_charset='utf8',
                    extend_existing=True)

    op.create_index('ix_storageServices_endpoint', 'storage_services', ['endpoint'], unique=False)
    op.create_index('ix_storageServices_status', 'storage_services', ['status'], unique=False)
    op.create_index('ix_storageServices_avail_size', 'storage_services', ['avail_size'], unique=False)
    op.create_index('ix_storageServices_file_system_uuid', 'storage_services', ['file_system_uuid'], unique=False)
    op.create_index('ix_storageServices_disk_wwn', 'storage_services', ['disk_wwn'], unique=False)
    op.create_index('ix_storageServices_updated_at', 'storage_services', ['updated_at'], unique=False)
    op.create_index('ix_storageServices_deleted', 'storage_services', ['deleted'], unique=False)


def upgrade():
    _add_storage_services_table()
