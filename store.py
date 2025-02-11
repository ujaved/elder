from supabase import create_client, Client
from enum import Enum
from datetime import date, datetime, time
from dataclasses import dataclass, field


class Role(Enum):
    GUARDIAN = "GUARDIAN"
    CAREGIVER = "CAREGIVER"


class Caregiver_Status(Enum):
    INVITED = "INVITED"
    ACCEPTED = "ACCEPTED"


@dataclass
class CaregiverNote:
    note: str
    created_at: datetime

    def serialize_to_db(self) -> dict:
        return {
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }

    @staticmethod
    def deserialize_from_db(note: dict):
        return CaregiverNote(note["note"], datetime.fromisoformat(note["created_at"]))


@dataclass
class Caregiver:
    id: str
    status: Caregiver_Status
    notes: list[CaregiverNote] = field(default_factory=list)

    def serialize_to_db(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def deserialize_from_db(caregiver: dict):
        return Caregiver(
            caregiver["caregiver_id"],
            Caregiver_Status(caregiver["status"]),
            [CaregiverNote.deserialize_from_db(note) for note in caregiver["notes"]],
        )


@dataclass
class Question:
    question: str
    answer: str
    updated_at: datetime = datetime.now()

    def serialize_to_db(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "updated_at": self.updated_at.isoformat(),
        }

    @staticmethod
    def deserialize_from_db(question: dict):
        return Question(
            question["question"],
            question["answer"],
            datetime.fromisoformat(question["updated_at"]),
        )


@dataclass
class Task:
    content: str
    start_time: time | None = None
    end_time: time | None = None
    status: bool = False
    updated_at: datetime = datetime.now()

    def serialize_to_db(self, serialize_time: bool = True) -> dict:
        return {
            "content": self.content,
            "status": self.status,
            "updated_at": self.updated_at.isoformat(),
            "start_time": (
                self.start_time.isoformat()
                if self.start_time and serialize_time
                else self.start_time
            ),
            "end_time": (
                self.end_time.isoformat()
                if self.end_time and serialize_time
                else self.end_time
            ),
        }

    @staticmethod
    def deserialize_from_db(task: dict):
        return Task(
            content=task["content"],
            start_time=(
                time.fromisoformat(task["start_time"]) if task["start_time"] else None
            ),
            end_time=time.fromisoformat(task["end_time"]) if task["end_time"] else None,
            status=task["status"],
            updated_at=datetime.fromisoformat(task["updated_at"]),
        )


@dataclass
class CarePlan:
    id: str
    guardian_id: str
    date: date
    created_at: datetime
    caregivers: list[Caregiver] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)

    @staticmethod
    def deserialize_from_db(cp: dict, caregivers: list[Caregiver]):
        return CarePlan(
            id=cp["id"],
            guardian_id=cp["guardian_id"],
            date=date.fromisoformat(cp["date"]),
            created_at=datetime.fromisoformat(cp["created_at"]),
            tasks=[Task.deserialize_from_db(task) for task in cp["tasks"]],
            questions=[Question.deserialize_from_db(q) for q in cp["questions"]],
            caregivers=caregivers,
        )


class DBClient:
    def __init__(self, supabase_url: str, supabase_key: str) -> Client:
        self.client = create_client(supabase_url, supabase_key)

    def sign_in(self, email: str, password: str):
        return self.client.auth.sign_in_with_password(
            {"email": email, "password": password}
        ).user

    def get_user(
        self, user_id: str | None = None, jwt: str | None = None
    ) -> dict | None:
        if user_id:
            try:
                return self.client.auth.admin.get_user_by_id(user_id).user
            except:
                return None
        else:
            return self.client.auth.get_user(jwt).user

    def get_caregiver_user(self, email: str) -> dict | None:
        response = self.client.auth.admin.list_users()
        for user in response:
            if (
                user.email == email
                and user.user_metadata["role"] == Role.CAREGIVER.value
            ):
                return user
        return None

    def update_user_password(self, user_id: str, password: str):
        return self.client.auth.admin.update_user_by_id(
            user_id, {"password": password}
        ).user

    def update_user_metadata(self, user_id: str, metadata: dict):
        self.client.auth.admin.update_user_by_id(user_id, {"user_metadata": metadata})

    def invite_user_by_email(self, email: str, first_name: str, last_name: str) -> dict:
        return self.client.auth.admin.invite_user_by_email(
            email,
            options={
                "data": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": Role.GUARDIAN.value,
                }
            },
        ).user

    def sign_in_with_otp(
        self,
        email: str,
        redirect_url: str,
        care_plan_id: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ):
        options = {"email_redirect_to": redirect_url}
        if first_name:
            options["data"] = {
                "first_name": first_name,
                "last_name": last_name,
                "role": Role.CAREGIVER.value,
                "care_plan_id": care_plan_id,
            }
        self.client.auth.sign_in_with_otp({"email": email, "options": options})

    def create_care_plan(self, guardian_id: str, date: date) -> CarePlan:
        cp = (
            self.client.table("care_plan")
            .insert({"guardian_id": guardian_id, "date": date.isoformat()})
            .execute()
            .data[0]
        )
        return CarePlan.deserialize_from_db(cp, [])

    def delete_care_plan(self, care_plan_id: str):
        return self.client.table("care_plan").delete().eq("id", care_plan_id).execute()

    def create_caregiver_in_care_plan(self, caregiver_id: str, care_plan_id: str):
        self.client.table("caregiver").insert(
            {
                "caregiver_id": caregiver_id,
                "care_plan_id": care_plan_id,
                "status": Caregiver_Status.INVITED.value,
            }
        ).execute()

    def update_caregiver_status(
        self, care_plan_id: str, caregiver_id: str, status: Caregiver_Status
    ):
        self.client.table("caregiver").update({"status": status.value}).eq(
            "care_plan_id", care_plan_id
        ).eq("caregiver_id", caregiver_id).execute()

    def update_care_plan(
        self,
        care_plan_id: str,
        tasks: list[Task] | None = None,
        questions: list[Question] | None = None,
    ) -> CarePlan:
        if tasks is not None:
            update = {"tasks": [Task.serialize_to_db(task) for task in tasks]}
            if questions:
                update["questions"] = [Question.serialize_to_db(q) for q in questions]
        elif questions is not None:
            update = {"questions": [Question.serialize_to_db(q) for q in questions]}
            if tasks:
                update["tasks"] = [Task.serialize_to_db(task) for task in tasks]
        updated = (
            self.client.table("care_plan")
            .update(update)
            .eq("id", care_plan_id)
            .execute()
            .data[0]
        )
        return CarePlan.deserialize_from_db(updated, self.get_caregivers(updated["id"]))

    def get_caregiver_ids_for_guardian(self, guardian_id: str) -> list[str]:
        data = (
            self.client.table("caregiver")
            .select("caregiver_id, care_plan!inner(id)")
            .eq("care_plan.guardian_id", guardian_id)
            .execute()
            .data
        )
        return [d["caregiver_id"] for d in data]

        """
        caregiver_ids = (
            self.client.table("care_plan")
            .select("caregiver_id")
            .eq("guardian_id", guardian_id)
            .not_.is_("caregiver_id", "null")
            .execute()
            .data
        )
        return list({c["caregiver_id"] for c in caregiver_ids})
        """

    def get_caregivers(
        self, care_plan_id: str, caregiver_id: str | None = None
    ) -> list[Caregiver]:
        if caregiver_id:
            cgs = (
                self.client.table("caregiver")
                .select("*")
                .eq("care_plan_id", care_plan_id)
                .eq("caregiver_id", caregiver_id)
                .execute()
                .data
            )
        else:
            cgs = (
                self.client.table("caregiver")
                .select("*")
                .eq("care_plan_id", care_plan_id)
                .execute()
                .data
            )
        return [Caregiver.deserialize_from_db(cg) for cg in cgs]

    def get_care_plans(self, guardian_id: str) -> list[CarePlan]:
        cps = (
            self.client.table("care_plan")
            .select("*")
            .eq("guardian_id", guardian_id)
            .execute()
            .data
        )
        return [
            CarePlan.deserialize_from_db(cp, self.get_caregivers(cp["id"]))
            for cp in cps
        ]

    def get_care_plan(self, care_plan_id: str) -> CarePlan | None:
        cp = (
            self.client.table("care_plan")
            .select("*")
            .eq("id", care_plan_id)
            .execute()
            .data
        )
        if cp:
            cp = cp[0]
        else:
            return None
        return CarePlan.deserialize_from_db(cp, self.get_caregivers(care_plan_id))
