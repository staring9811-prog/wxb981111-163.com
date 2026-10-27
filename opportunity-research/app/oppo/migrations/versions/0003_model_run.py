"""变量关系 model runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('model_run',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('mode', sa.String(length=8), nullable=False),
    sa.Column('compute_run_id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('config_version_id', sa.Integer(), nullable=True),
    sa.Column('adjust_hash', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('verdict', sa.String(length=32), nullable=True),
    sa.Column('result_json', sa.Text(), nullable=True),
    sa.Column('started_at', sa.String(length=32), nullable=True),
    sa.Column('ended_at', sa.String(length=32), nullable=True),
    sa.Column('created_by', sa.String(length=64), server_default='wen', nullable=False),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_model_run_cat', 'model_run', ['category_id', 'mode'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_model_run_cat', table_name='model_run')
    op.drop_table('model_run')
