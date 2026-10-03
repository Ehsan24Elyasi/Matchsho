# Pilot browser contract

All URLs below are backend paths; the browser prefixes `/api`. Mutations require the CSRF cookie/header, credentials included. Errors use `{detail: message}` or Pydantic field details. Lists use `{items,total,page,limit}`. Private responses are no-store. No student IDs, emails or answers in peer DTOs.

## Authentication

`GET /pilot/config` includes `email_verification_required` (default false). With verification disabled, `POST /auth/register` accepts `{email,password,name,class_name,student_id,gender}` and returns 201, the owner DTO and HttpOnly session cookies. Registration requires CSRF, uses Argon2id, preserves existing identities/operator restrictions and creates the enrollment automatically. It sends no email. `email_verified` remains false. Login uses `POST /auth/login` with email/password. Activation, resend, verification and email password-reset endpoints return 404 while disabled; queued authentication messages are cancelled before delivery.

Only the explicit optional verification mode accepts student ID/email claims and returns 202 before activation through an emailed link.

## Questionnaire

- `GET /questionnaire/schema`: `{version:2,scoring_version:'2',dimensions:[{key,label,kind:'time'|'choice',required,options:[{value,label}]}],capacities:[2,4,...]}`. Keys: sleep,wake,cleaning,guests,noise,tobacco(optional).
- `GET /questionnaire/me`: `{version:2,revision,answers,capacities,complete}`.
- `PUT /questionnaire/me`: `{version:2,answers:{sleep:{own:'23:00',accepted:['22:00','01:00'],importance:2,hard:false},cleaning:{own:'weekly',accepted:['daily','weekly'],importance:2,hard:false},...},capacities:[4]}`. Full current-schema submission required.
- `GET/PUT /questionnaire/draft`: same body, incomplete allowed; GET returns null draft as `{version:2,answers:{},capacities:[]}`. Server-owned; do not persist answers to browser storage.

## Discovery and groups

- `GET /matches?page=1&limit=12`: list envelope. Items `{kind:'user'|'group',id,user:{id,name,class_name},group:null|{id,capacity,members:[{id,name,class_name}]},score,explanations:[],capacities:[],can_invite:true}`. user on a group item is a representative for profile navigation.
- `GET /profiles/{user_id}`: `{id,name,class_name,score,explanations,group,capacities,can_invite}`; access has a purpose-aware policy.
- `GET /group/me`: `{id,capacity,membership_revision,members:[{id,name,class_name}],room:null|{id,number,dormitory,capacity},departure:null|{id,status,reason}}`; no group is 404.
- `DELETE /group/me`: unassigned departure only.
- `POST /group/me/departure`: `{reason}` submits individual operator case.
- `GET /rooms`: list envelope of `{id,number,dormitory,capacity,current_occupancy,pool,cycle,available}`.

## Invitations

- `GET /requests`: list envelope of `{id,initiator:{id,name,class_name},candidate:{id,name,class_name},group,capacity,status,expires_at,approvals:[user_id],required_approvals:[user_id],can_approve,can_reject,can_cancel,can_reconfirm,reason}`.
- `POST /requests`: `{receiver_id,capacity}` for a solo target; `{group_id,capacity}` for solo requesting entry to an existing group. A grouped sender inviting a solo target still uses receiver_id. No group merge.
- `POST /requests/{id}/approve|reject|cancel|reconfirm`: no body required; latest invitation response. Reconfirmation resets the snapshot and requires new approvals.
- `GET /notifications`: envelope `{id,kind,message,entity_type,entity_id,read,created_at}`.
- `POST /notifications/{id}/read`: no domain mutation other than read marker.

## Operator domain routes

- `GET /admin/groups`, `/admin/rooms`, `/admin/departures`, `/admin/audit`: paginated envelopes, optional `q`.
- `POST /admin/rooms`: `{number,dormitory,capacity,pool,cycle,reason}`.
- `PATCH /admin/rooms/{id}`: same editable fields + reason; active target-capacity invariants preserved.
- `POST /admin/groups/{id}/allocation`: `{room_id,reason}` performs assign or atomic move.
- `DELETE /admin/groups/{id}/allocation`: `{reason}` only administrator.
- `POST /admin/departures/{id}/resolve`: `{decision:'approved'|'rejected',reason}`.
- `DELETE /admin/groups/{group_id}/members/{user_id}`: `{reason}` removes one member safely.
- `GET /admin/export?resource=groups|rooms`: formula-safe CSV, no questionnaire answers.

Security/account/roster/outbox routes are supplied by the security module; see its API contract and OpenAPI during integration.
