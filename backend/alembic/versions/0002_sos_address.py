"""SOS alerts: free-text address / landmark given by the user with the alert.

Revision ID: 0002_sos_address
Revises: 0001_baseline
Create Date: 2026-10-11 15:30:00+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# pylint: disable=invalid-name,no-member  # Alembic's revision globals and ``op`` proxy

# revision identifiers, used by Alembic.
revision: str = '0002_sos_address'
down_revision: Union[str, None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('hub_sos_alerts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address', sa.String(length=300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('hub_sos_alerts', schema=None) as batch_op:
        batch_op.drop_column('address')
