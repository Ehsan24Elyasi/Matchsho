"""Initial production schema and questionnaire seed data."""

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("class_name", sa.String(100), nullable=False),
        sa.Column("student_id", sa.String(50), nullable=False),
        sa.Column("gender", sa.String(20), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("gender IN ('male', 'female', 'other')", name="ck_users_gender"),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("student_id", name="uq_users_student_id"),
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("jti", name="uq_refresh_sessions_jti"),
    )
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="ck_auth_tokens_purpose"),
        sa.UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="scale"),
        sa.Column("min_value", sa.Integer(), nullable=True),
        sa.Column("max_value", sa.Integer(), nullable=True),
        sa.Column("options_json", sa.Text(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", name="uq_questions_key"),
    )
    op.create_table(
        "answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "question_id", name="uq_answers_user_question"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("dormitory", sa.String(100), nullable=False),
        sa.Column("current_occupancy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_rooms_capacity_positive"),
        sa.CheckConstraint("current_occupancy >= 0", name="ck_rooms_occupancy_nonnegative"),
        sa.CheckConstraint("current_occupancy <= capacity", name="ck_rooms_occupancy_within_capacity"),
        sa.UniqueConstraint("dormitory", "number", name="uq_rooms_dormitory_number"),
    )

    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capacity", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("is_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_groups_capacity_positive"),
    )

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_member"),
        sa.UniqueConstraint("user_id", name="uq_group_members_user_id"),
    )

    op.create_table(
        "room_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_id", sa.Integer(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", name="uq_room_assignments_group_id"),
    )

    op.create_table(
        "roommate_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("receiver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("active_pair_key", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sender_id <> receiver_id", name="ck_requests_distinct_users"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'cancelled')", name="ck_request_status"),
        sa.UniqueConstraint("active_pair_key", name="uq_requests_active_pair"),
    )
    op.create_index("ix_requests_sender_status", "roommate_requests", ["sender_id", "status"])
    op.create_index("ix_requests_receiver_status", "roommate_requests", ["receiver_id", "status"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    question_table = sa.table(
        "questions",
        sa.column("key", sa.String),
        sa.column("text", sa.String),
        sa.column("kind", sa.String),
        sa.column("min_value", sa.Integer),
        sa.column("max_value", sa.Integer),
        sa.column("options_json", sa.Text),
        sa.column("weight", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    questions = [
        ("hygiene", "بهداشت هم‌اتاقی برای شما چقدر اهمیت دارد؟", "scale", 1, 5, [], 15),
        ("socializing", "نسبت به رفیق‌بازی و آوردن دوستان به اتاق چقدر حساس هستید؟", "scale", 1, 5, [], 15),
        ("smoking", "نسبت به مصرف دخانیات توسط هم‌اتاقی چقدر حساس هستید؟", "scale", 1, 5, [], 15),
        ("noise", "سر و صدای هم‌اتاقی برای شما چقدر اهمیت دارد؟", "scale", 1, 5, [], 15),
        ("beliefs", "اعتقادات هم‌اتاقی برای شما چقدر اهمیت دارد؟", "scale", 1, 5, [], 15),
        ("sleep", "ساعت خواب هم‌اتاقی برای شما چقدر اهمیت دارد؟", "scale", 1, 5, [], 15),
        ("room_size", "اتاق چند نفره را ترجیح می‌دهید؟", "choice", None, None, [2, 4, 8, 12], 10),
    ]
    op.bulk_insert(
        question_table,
        [
            {
                "key": key,
                "text": text,
                "kind": kind,
                "min_value": minimum,
                "max_value": maximum,
                "options_json": json.dumps(options),
                "weight": weight,
                "created_at": datetime.now(timezone.utc),
            }
            for key, text, kind, minimum, maximum, options, weight in questions
        ],
    )


def downgrade() -> None:
    for table in (
        "audit_logs",
        "roommate_requests",
        "room_assignments",
        "group_members",
        "groups",
        "rooms",
        "answers",
        "questions",
        "auth_tokens",
        "refresh_sessions",
        "users",
    ):
        op.drop_table(table)
