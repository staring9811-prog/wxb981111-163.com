"""reviewed data adjustments over imported packages

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-27 08:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('data_adjustment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('batch', sa.String(length=16), nullable=True),
    sa.Column('file_code', sa.String(length=4), nullable=False),
    sa.Column('child', sa.String(length=16), nullable=False),
    sa.Column('month', sa.String(length=7), nullable=True),
    sa.Column('field', sa.String(length=32), nullable=False),
    sa.Column('old_value', sa.Text(), nullable=True),
    sa.Column('proposed_value', sa.Text(), nullable=True),
    sa.Column('final_value', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=8), nullable=False),
    sa.Column('decided_by', sa.String(length=64), nullable=True),
    sa.Column('decided_at', sa.String(length=32), nullable=True),
    sa.Column('decision_note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.String(length=64), server_default='wen', nullable=False),
    sa.Column('created_at', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index('ix_data_adjustment_pkg', 'data_adjustment', ['package_id', 'status'], unique=False)
    with op.batch_alter_table('compute_run') as batch_op:
        batch_op.add_column(sa.Column('adjust_hash', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('compute_run') as batch_op:
        batch_op.drop_column('adjust_hash')
    op.drop_index('ix_data_adjustment_pkg', table_name='data_adjustment')
    op.drop_table('data_adjustment')
