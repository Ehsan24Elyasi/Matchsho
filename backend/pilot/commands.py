"""Actor-scoped receipts for safe replay after an intervening domain change."""
import hashlib
import json

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from pilot.domain_models import CommandReceipt


class Command:
    """Use after the domain lock and before reading mutable business state."""
    def __init__(self, db, actor, action, payload, request):
        self.db, self.actor, self.action = db, actor, action
        self.key = request.headers.get("Idempotency-Key") if request else None
        self.digest = hashlib.sha256(json.dumps(jsonable_encoder(payload), sort_keys=True).encode()).hexdigest()
        self.cached = None
        if self.key:
            if len(self.key) > 100:
                raise HTTPException(422, "کلید درخواست معتبر نیست")
            record = db.query(CommandReceipt).filter_by(actor_id=actor.id, action=action, key=self.key).first()
            if record:
                if record.payload_hash != self.digest:
                    raise HTTPException(409, "این کلید قبلاً برای درخواست دیگری استفاده شده است")
                self.cached = record.result

    def finish(self, result):
        if self.key and self.cached is None:
            self.db.add(CommandReceipt(actor_id=self.actor.id, action=self.action, key=self.key,
                                       payload_hash=self.digest, result=jsonable_encoder(result)))
        return result
