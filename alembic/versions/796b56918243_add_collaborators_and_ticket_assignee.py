"""add collaborators and ticket assignee

Revision ID: 796b56918243
Revises: 324d9e38d957
Create Date: 2026-08-29 13:22:05.416042

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '796b56918243'
down_revision: Union[str, None] = '324d9e38d957'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ticket_collaborators',
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('ticket_id', 'user_id')
    )

    # primary_assignee_id must end up NOT NULL, but tickets created before
    # this migration have no assignee. Add it nullable, backfill existing
    # rows to the earliest-created agent (a placeholder choice -- a real
    # system would need a manual triage pass, not a silent default), then
    # tighten the column. See docs/decisions.md.
    with op.batch_alter_table('tickets') as batch_op:
        batch_op.add_column(sa.Column('primary_assignee_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_tickets_primary_assignee_id_users', 'users', ['primary_assignee_id'], ['id']
        )

    connection = op.get_bind()
    fallback_agent_id = connection.execute(
        sa.text("SELECT id FROM users WHERE role = 'agent' ORDER BY id LIMIT 1")
    ).scalar()
    if fallback_agent_id is not None:
        connection.execute(
            sa.text(
                "UPDATE tickets SET primary_assignee_id = :agent_id "
                "WHERE primary_assignee_id IS NULL"
            ),
            {"agent_id": fallback_agent_id},
        )

    with op.batch_alter_table('tickets') as batch_op:
        batch_op.alter_column('primary_assignee_id', nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('tickets') as batch_op:
        batch_op.drop_constraint('fk_tickets_primary_assignee_id_users', type_='foreignkey')
        batch_op.drop_column('primary_assignee_id')
    op.drop_table('ticket_collaborators')
