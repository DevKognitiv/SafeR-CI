"""Baseline: the SafeR Hub schema exactly as ``Base.metadata.create_all`` produced it at commit b8880be.

Hubs created before migrations existed already have these tables (and no ``hub_alembic_version`` table); the
runtime stamps them with this revision
instead of running it (see ``app.hub.migrations``).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11 15:17:38+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# pylint: disable=invalid-name,no-member  # Alembic's revision globals and ``op`` proxy

# revision identifiers, used by Alembic.
revision: str = '0001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('hub_homes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('address', sa.String(length=255), nullable=True),
    sa.Column('security_mode', sa.String(length=20), nullable=False),
    sa.Column('alarm_active', sa.Boolean(), nullable=False),
    sa.Column('alarm_device_id', sa.String(length=36), nullable=True),
    sa.Column('security_changed_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('hub_users',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=40), nullable=True),
    sa.Column('locale', sa.String(length=10), nullable=False),
    sa.Column('avatar_url', sa.String(length=500), nullable=True),
    sa.Column('is_admin', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_users_email', 'hub_users', ['email'], unique=True)

    op.create_table('hub_automations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('match', sa.String(length=10), nullable=False),
    sa.Column('triggers', sa.JSON(), nullable=False),
    sa.Column('conditions', sa.JSON(), nullable=False),
    sa.Column('actions', sa.JSON(), nullable=False),
    sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_automations_home_id', 'hub_automations', ['home_id'], unique=False)

    op.create_table('hub_home_members',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['hub_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('home_id', 'user_id', name='uq_home_member')
    )
    op.create_index('ix_hub_home_members_home_id', 'hub_home_members', ['home_id'], unique=False)
    op.create_index('ix_hub_home_members_user_id', 'hub_home_members', ['user_id'], unique=False)

    op.create_table('hub_integrations',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('brand', sa.String(length=40), nullable=False),
    sa.Column('key', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('credentials_enc', sa.Text(), nullable=True),
    sa.Column('webhook_secret', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('home_id', 'key', name='uq_integration_key')
    )
    op.create_index('ix_hub_integrations_brand', 'hub_integrations', ['brand'], unique=False)
    op.create_index('ix_hub_integrations_home_id', 'hub_integrations', ['home_id'], unique=False)

    op.create_table('hub_messages',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('device_id', sa.String(length=36), nullable=True),
    sa.Column('severity', sa.String(length=20), nullable=False),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_messages_home_id', 'hub_messages', ['home_id'], unique=False)
    op.create_index('ix_message_home_created', 'hub_messages', ['home_id', 'created_at'], unique=False)

    op.create_table('hub_push_tokens',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('platform', sa.String(length=20), nullable=False),
    sa.Column('token', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['hub_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    op.create_index('ix_hub_push_tokens_user_id', 'hub_push_tokens', ['user_id'], unique=False)

    op.create_table('hub_rooms',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('icon', sa.String(length=60), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_rooms_home_id', 'hub_rooms', ['home_id'], unique=False)

    op.create_table('hub_scenes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('icon', sa.String(length=60), nullable=True),
    sa.Column('color', sa.String(length=20), nullable=True),
    sa.Column('actions', sa.JSON(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('last_run_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_scenes_home_id', 'hub_scenes', ['home_id'], unique=False)

    op.create_table('hub_sos_alerts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('lat', sa.Float(), nullable=True),
    sa.Column('lon', sa.Float(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('forwarded', sa.Boolean(), nullable=False),
    sa.Column('incident_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_hub_sos_alerts_home_id', 'hub_sos_alerts', ['home_id'], unique=False)

    op.create_table('hub_devices',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('room_id', sa.String(length=36), nullable=True),
    sa.Column('integration_id', sa.String(length=36), nullable=True),
    sa.Column('parent_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('brand', sa.String(length=40), nullable=False),
    sa.Column('protocol', sa.String(length=40), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('manufacturer', sa.String(length=120), nullable=True),
    sa.Column('firmware', sa.String(length=120), nullable=True),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('online', sa.Boolean(), nullable=False),
    sa.Column('icon', sa.String(length=60), nullable=True),
    sa.Column('capabilities', sa.JSON(), nullable=False),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('credentials_enc', sa.Text(), nullable=True),
    sa.Column('webhook_secret', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['home_id'], ['hub_homes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['integration_id'], ['hub_integrations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_id'], ['hub_devices.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['room_id'], ['hub_rooms.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('home_id', 'brand', 'external_id', name='uq_device_external')
    )
    op.create_index('ix_device_home_room', 'hub_devices', ['home_id', 'room_id'], unique=False)
    op.create_index('ix_hub_devices_brand', 'hub_devices', ['brand'], unique=False)
    op.create_index('ix_hub_devices_category', 'hub_devices', ['category'], unique=False)
    op.create_index('ix_hub_devices_home_id', 'hub_devices', ['home_id'], unique=False)

    op.create_table('hub_device_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('device_id', sa.String(length=36), nullable=False),
    sa.Column('home_id', sa.String(length=36), nullable=False),
    sa.Column('type', sa.String(length=60), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['device_id'], ['hub_devices.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_device_event_device_created', 'hub_device_events', ['device_id', 'created_at'], unique=False)
    op.create_index('ix_hub_device_events_device_id', 'hub_device_events', ['device_id'], unique=False)
    op.create_index('ix_hub_device_events_home_id', 'hub_device_events', ['home_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_hub_device_events_home_id', table_name='hub_device_events')
    op.drop_index('ix_hub_device_events_device_id', table_name='hub_device_events')
    op.drop_index('ix_device_event_device_created', table_name='hub_device_events')

    op.drop_table('hub_device_events')
    op.drop_index('ix_hub_devices_home_id', table_name='hub_devices')
    op.drop_index('ix_hub_devices_category', table_name='hub_devices')
    op.drop_index('ix_hub_devices_brand', table_name='hub_devices')
    op.drop_index('ix_device_home_room', table_name='hub_devices')

    op.drop_table('hub_devices')
    op.drop_index('ix_hub_sos_alerts_home_id', table_name='hub_sos_alerts')

    op.drop_table('hub_sos_alerts')
    op.drop_index('ix_hub_scenes_home_id', table_name='hub_scenes')

    op.drop_table('hub_scenes')
    op.drop_index('ix_hub_rooms_home_id', table_name='hub_rooms')

    op.drop_table('hub_rooms')
    op.drop_index('ix_hub_push_tokens_user_id', table_name='hub_push_tokens')

    op.drop_table('hub_push_tokens')
    op.drop_index('ix_message_home_created', table_name='hub_messages')
    op.drop_index('ix_hub_messages_home_id', table_name='hub_messages')

    op.drop_table('hub_messages')
    op.drop_index('ix_hub_integrations_home_id', table_name='hub_integrations')
    op.drop_index('ix_hub_integrations_brand', table_name='hub_integrations')

    op.drop_table('hub_integrations')
    op.drop_index('ix_hub_home_members_user_id', table_name='hub_home_members')
    op.drop_index('ix_hub_home_members_home_id', table_name='hub_home_members')

    op.drop_table('hub_home_members')
    op.drop_index('ix_hub_automations_home_id', table_name='hub_automations')

    op.drop_table('hub_automations')
    op.drop_index('ix_hub_users_email', table_name='hub_users')

    op.drop_table('hub_users')
    op.drop_table('hub_homes')
