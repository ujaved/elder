from supabase import create_client, Client
from enum import Enum
from datetime import date
from chatbot import Task


class Role(Enum):
    GUARDIAN = "GUARDIAN"
    CARER = "CARER"


class Carer_Status(Enum):
    INVITED = "INVITED"
    ACCEPTED = "ACCEPTED"


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

    def get_carer(self, email: str) -> dict | None:
        response = self.client.auth.admin.list_users()
        for user in response:
            if user.email == email and user.user_metadata["role"] == Role.CARER.value:
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
                "role": Role.CARER.value,
                "care_plan_id": care_plan_id,
            }
        self.client.auth.sign_in_with_otp({"email": email, "options": options})

    def create_care_plan(self, guardian_id: str, date: date) -> dict:
        return (
            self.client.table("care_plan")
            .insert({"guardian_id": guardian_id, "date": date.isoformat()})
            .execute()
            .data[0]
        )

    def delete_care_plan(self, care_plan_id: str):
        return self.client.table("care_plan").delete().eq("id", care_plan_id).execute()

    def create_carer_in_care_plan(self, carer_id: str, care_plan_id: str):
        self.client.table("carer").insert(
            {
                "carer_id": carer_id,
                "care_plan_id": care_plan_id,
                "carer_status": Carer_Status.INVITED.value,
            }
        ).execute()

    def update_carer_status(
        self, care_plan_id: str, carer_id: str, carer_status: Carer_Status
    ):
        self.client.table("carer").update({"carer_status": carer_status.value}).eq(
            "care_plan_id", care_plan_id
        ).eq("carer_id", carer_id).execute()

    def update_care_plan(
        self,
        care_plan_id: str,
        tasks: list[dict] | None = None,
        questions: list[dict] | None = None,
    ) -> dict:
        if tasks is not None:
            update = {"tasks": [Task.serialize_to_db(task) for task in tasks]}
            if questions:
                update["questions"] = [
                    Task.serialize_question_to_db(q) for q in questions
                ]
        elif questions is not None:
            update = {
                "questions": [Task.serialize_question_to_db(q) for q in questions]
            }
            if tasks:
                update["tasks"] = [Task.serialize_to_db(task) for task in tasks]
        updated = (
            self.client.table("care_plan")
            .update(update)
            .eq("id", care_plan_id)
            .execute()
            .data[0]
        )

        if updated["tasks"]:
            updated["tasks"] = [
                Task.deserialize_from_db(task) for task in updated["tasks"]
            ]
        if updated["questions"]:
            updated["questions"] = [
                Task.deserialize_question_from_db(q) for q in updated["questions"]
            ]
        return updated

    def get_carer_ids_for_guardian(self, guardian_id: str) -> list[str]:
        data = (
            self.client.table("carer")
            .select("carer_id, care_plan!inner(id)")
            .eq("care_plan.guardian_id", guardian_id)
            .execute()
            .data
        )
        return [d["carer_id"] for d in data]

        """
        carer_ids = (
            self.client.table("care_plan")
            .select("carer_id")
            .eq("guardian_id", guardian_id)
            .not_.is_("carer_id", "null")
            .execute()
            .data
        )
        return list({c["carer_id"] for c in carer_ids})
        """

    def get_carers(self, care_plan_id: str, carer_id: str | None = None) -> list[dict]:
        if carer_id:
            return (
                self.client.table("carer")
                .select("*")
                .eq("care_plan_id", care_plan_id)
                .eq("carer_id", carer_id)
                .execute()
                .data
            )
        else:
            return (
                self.client.table("carer")
                .select("*")
                .eq("care_plan_id", care_plan_id)
                .execute()
                .data
            )

    def get_care_plans(self, guardian_id: str) -> list[dict]:
        cps = (
            self.client.table("care_plan")
            .select("*")
            .eq("guardian_id", guardian_id)
            .execute()
            .data
        )
        for cp in cps:
            tasks = [Task.deserialize_from_db(task) for task in cp["tasks"]]
            cp["tasks"] = tasks
            questions = [Task.deserialize_question_from_db(q) for q in cp["questions"]]
            cp["questions"] = questions
        return cps

    def get_care_plan(self, care_plan_id: str) -> dict | None:
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
        tasks = [Task.deserialize_from_db(task) for task in cp["tasks"]]
        cp["tasks"] = tasks
        questions = [Task.deserialize_question_from_db(q) for q in cp["questions"]]
        cp["questions"] = questions
        return cp
