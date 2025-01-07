import streamlit as st
from store import DBClient, Role, Carer_Status
from datetime import date, datetime, time
from streamlit_calendar import calendar
from gotrue.errors import AuthApiError
from streamlit_url_fragment import get_fragment
import jwt
from streamlit_extras.stylable_container import stylable_container
from chatbot import generate_tasks_from_audio, Task, generate_answer_from_audio


calendar_options = {
    "headerToolbar": {
        "left": "prev,next",
        "center": "title",
    },
    "slotMinTime": "06:00:00",
    "slotMaxTime": "18:00:00",
    "initialView": "timeGridDay",
}


def init_connection() -> None:
    if "db_client" not in st.session_state:
        st.session_state["db_client"] = DBClient(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        )


def login_submit(is_login: bool):
    if is_login:
        if not st.session_state.login_email or not st.session_state.login_password:
            st.error("Please provide login information")
            return
        try:
            st.session_state["user"] = st.session_state.db_client.sign_in(
                st.session_state.login_email, st.session_state.login_password
            )
        except AuthApiError as e:
            st.error(e)
        return
    try:
        if (
            not st.session_state.register_email
            or not st.session_state.register_first_name
            or not st.session_state.register_last_name
        ):
            st.error("Please provide all requested information")
            return
        st.session_state.db_client.invite_user_by_email(
            st.session_state.register_email,
            st.session_state.register_first_name,
            st.session_state.register_last_name,
        )
        st.info("An email invite has been sent to your email")
    except AuthApiError as e:
        st.error(e)


def register_login():
    login_tab, register_tab = st.tabs(["Login", "Sign up"])
    with login_tab:
        with st.form("login_form", clear_on_submit=True):
            st.text_input("Email", key="login_email")
            st.text_input("Password", type="password", key="login_password")
            st.form_submit_button("Submit", on_click=login_submit, args=[True])

    with register_tab:
        with st.form("register", clear_on_submit=True):
            st.text_input("Email", key="register_email")
            st.text_input("First name", key="register_first_name")
            st.text_input("Last name", key="register_last_name")
            st.form_submit_button("Submit", on_click=login_submit, args=[False])


def reset_password(email: str, user_id: str):
    st.info("Please set your password")
    with st.form("login_form", clear_on_submit=True):
        st.text_input("Email", key="reset_password_email", value=email, disabled=True)
        st.text_input("Password", type="password", key="reset_password_password")
        st.text_input(
            "Confirm Password", type="password", key="reset_password_confirm_password"
        )
        st.form_submit_button("Submit", on_click=reset_password_submit, args=(user_id,))


def reset_password_submit(user_id: str):
    if (
        not st.session_state.reset_password_password
        or not st.session_state.reset_password_confirm_password
    ):
        st.error("Please enter password and confirm password")
        return
    if (
        st.session_state.reset_password_password
        != st.session_state.reset_password_confirm_password
    ):
        st.error("Passwords don't match")
        return
    try:
        st.session_state["user"] = st.session_state.db_client.update_user_password(
            user_id, st.session_state.reset_password_password
        )
    except AuthApiError as e:
        st.error(e)


def question_list_changed():
    if st.session_state.question_list_changed["deleted_rows"]:
        for r in st.session_state.question_list_changed["deleted_rows"]:
            del st.session_state.cur_care_plan["questions"][r]
        st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
            st.session_state.cur_care_plan["id"],
            questions=st.session_state.cur_care_plan["questions"],
        )

    if st.session_state.question_list_changed["edited_rows"]:
        for r, edit in st.session_state.question_list_changed["edited_rows"].items():
            if "question" in edit:
                st.session_state.cur_care_plan["questions"][r]["question"] = edit[
                    "question"
                ]
            if "answer" in edit:
                st.session_state.cur_care_plan["questions"][r]["answer"] = edit[
                    "answer"
                ]
            st.session_state.cur_care_plan["questions"][r][
                "updated_time"
            ] = datetime.now()

        st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
            st.session_state.cur_care_plan["id"],
            questions=st.session_state.cur_care_plan["questions"],
        )

    if st.session_state.question_list_changed["added_rows"]:
        added = []
        for r in st.session_state.question_list_changed["added_rows"]:
            if not r.get("question"):
                continue
            question = {
                "question": r.get("question"),
                "answer": "",
                "updated_at": datetime.now().isoformat(),
            }
            added.append(Task.deserialize_question_from_db(question))
        if added:
            st.session_state.cur_care_plan["questions"].extend(added)
            st.session_state.cur_care_plan = (
                st.session_state.db_client.update_care_plan(
                    st.session_state.cur_care_plan["id"],
                    questions=st.session_state.cur_care_plan["questions"],
                )
            )


def task_list_changed():
    if st.session_state.task_list_changed["deleted_rows"]:
        for r in st.session_state.task_list_changed["deleted_rows"]:
            del st.session_state.cur_care_plan["tasks"][r]
        st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
            st.session_state.cur_care_plan["id"],
            tasks=st.session_state.cur_care_plan["tasks"],
        )

    if st.session_state.task_list_changed["edited_rows"]:
        for r, edit in st.session_state.task_list_changed["edited_rows"].items():
            if "content" in edit:
                st.session_state.cur_care_plan["tasks"][r]["content"] = edit["content"]
            if "status" in edit:
                st.session_state.cur_care_plan["tasks"][r]["status"] = edit["status"]
            if "start_time" in edit:
                st.session_state.cur_care_plan["tasks"][r]["start_time"] = (
                    time.fromisoformat(edit["start_time"])
                )

            if "end_time" in edit:
                st.session_state.cur_care_plan["tasks"][r]["end_time"] = (
                    time.fromisoformat(edit["end_time"])
                )
            elif "start_time" in edit:
                start_time = st.session_state.cur_care_plan["tasks"][r]["start_time"]
                st.session_state.cur_care_plan["tasks"][r]["end_time"] = time(
                    hour=start_time.hour, minute=start_time.minute + 30
                )
            st.session_state.cur_care_plan["tasks"][r]["updated_time"] = datetime.now()

        st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
            st.session_state.cur_care_plan["id"],
            tasks=st.session_state.cur_care_plan["tasks"],
        )

    if st.session_state.task_list_changed["added_rows"]:
        added = []
        for r in st.session_state.task_list_changed["added_rows"]:
            content = r.get("content")
            if not content:
                continue
            task = {
                "content": content,
                "status": False,
                "start_time": r.get("start_time"),
                "end_time": r.get("end_time"),
                "updated_at": datetime.now().isoformat(),
            }
            added.append(Task.deserialize_from_db(task))
        if added:
            st.session_state.cur_care_plan["tasks"].extend(added)
            st.session_state.cur_care_plan = (
                st.session_state.db_client.update_care_plan(
                    st.session_state.cur_care_plan["id"],
                    tasks=st.session_state.cur_care_plan["tasks"],
                )
            )


def render_carer_status():
    carer = DBClient(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]).get_user(
        user_id=st.session_state.cur_care_plan["carer_id"]
    )
    name = carer.user_metadata["first_name"] + " " + carer.user_metadata["last_name"]
    carer_status = Carer_Status(st.session_state.cur_care_plan.get("carer_status"))
    if carer_status == Carer_Status.INVITED:
        st.error(f"Carer Invitation is pending for {name}.")
        if st.button("Reinvite"):
            add_carer_cb(reinvite=True)
    else:
        st.info(f"Carer {name} has accepted the invitation to this care plan.")


def delete_plan_cb():
    st.session_state.db_client.delete_care_plan(st.session_state.cur_care_plan["id"])
    st.session_state.pop("cur_care_plan", None)
    st.session_state.pop("date", None)


@st.fragment(run_every="10s")
def rerender_care_plan():
    updated = st.session_state.db_client.get_care_plan(
        st.session_state["cur_care_plan"]["id"]
    )
    highlight_last_row = False
    if len(updated["tasks"]) > len(st.session_state["cur_care_plan"]["tasks"]):
        highlight_last_row = True
    st.session_state["cur_care_plan"] = updated
    render_care_plan(highlight_last_row)


def render_tasks(disabled_columns: list[str], container):
    container.subheader("Tasks")
    tasks = sorted(
        st.session_state.cur_care_plan["tasks"], key=lambda t: t.get("updated_at")
    )
    container.data_editor(
        tasks,
        column_config={
            "status": st.column_config.CheckboxColumn(),
            "start_time": st.column_config.TimeColumn(),
            "end_time": st.column_config.TimeColumn(),
        },
        column_order=("content", "start_time", "end_time", "status"),
        disabled=disabled_columns,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key="task_list_changed",
        on_change=task_list_changed,
    )
    # if highlight_last_row:
    #    df = df.style.map(
    #        lambda _: "background-color: red;", subset=(df.index[-1], slice(None))
    #    )


def render_questions(container):
    container.subheader("Questions")
    if date.fromisoformat(st.session_state.cur_care_plan["date"]) < date.today():
        container.dataframe(
            st.session_state.cur_care_plan["questions"],
            hide_index=True,
            use_container_width=True,
            column_order=(
                "question",
                "answer",
            ),
        )
        return
    role = Role(st.session_state.user.user_metadata["role"])
    if role == Role.GUARDIAN:
        container.data_editor(
            st.session_state.cur_care_plan["questions"],
            column_order=("question", "answer"),
            disabled=["answer"],
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="question_list_changed",
            on_change=question_list_changed,
        )
        return
    # below is carer logic: answered questions are shown in data editor
    # and answered questions are shown with audio input
    answered_questions = [
        q for q in st.session_state.cur_care_plan["questions"] if q["answer"]
    ]
    unanswered_questions = [
        q for q in st.session_state.cur_care_plan["questions"] if not q["answer"]
    ]
    if answered_questions:
        container.data_editor(
            answered_questions,
            column_order=("question", "answer"),
            disabled=["question"],
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="question_list_changed",
            on_change=question_list_changed,
        )
    q_col, a_col = container.columns(2)
    for i, q in enumerate(unanswered_questions):
        q_col.text(q["question"])
        a_col.audio_input(
            "Please record your answer",
            key=f"answer_{i}",
            on_change=audio_answer_cb,
            args=[answered_questions, unanswered_questions, i, container],
        )


def audio_answer_cb(
    answered_questions: list[dict],
    unanswered_questions: list[dict],
    unanswered_idx: int,
    container,
):
    with container, st.spinner("Generating answer transcript"):
        key = f"answer_{unanswered_idx}"
        unanswered_questions[unanswered_idx]["answer"] = generate_answer_from_audio(
            st.session_state[key], unanswered_questions[unanswered_idx]["question"]
        )
        unanswered_questions[unanswered_idx]["updated_at"] = datetime.now()
    st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
        st.session_state.cur_care_plan["id"],
        questions=answered_questions + unanswered_questions,
    )


def render_care_plan(highlight_last_row: bool = False):
    dt = st.session_state.cur_care_plan["date"]
    st.info(f"Care plan for {dt}")
    role = Role(st.session_state.user.user_metadata["role"])
    col1, col2 = st.columns(2)
    if role == Role.GUARDIAN and date.fromisoformat(dt) >= date.today():
        # editable by guardian

        with stylable_container(
            key="delete_care_plan",
            css_styles="""
              button{
               float: right;
              }
              """,
        ):
            st.button("Delete plan", type="primary", on_click=delete_plan_cb)

        if not st.session_state.cur_care_plan["carer_status"]:
            add_carer()
            return

        render_carer_status()

        if st.session_state.cur_care_plan["tasks"]:
            render_tasks(disabled_columns=["status"], container=col1)
            render_questions(st.container())
        else:
            audio = st.audio_input(
                "Please record a care plan memo containing instructions and/or questions"
            )
            if audio:
                with st.spinner("Generating task and question lists"):
                    tasks, questions = generate_tasks_from_audio(audio)

                st.session_state["cur_care_plan"] = (
                    st.session_state.db_client.update_care_plan(
                        st.session_state.cur_care_plan["id"],
                        tasks=tasks,
                        questions=questions,
                    )
                )
    else:
        disabled_columns = ["content", "start_time", "end_time"]
        if date.fromisoformat(dt) < date.today():
            disabled_columns.append("status")
        render_tasks(disabled_columns=disabled_columns, container=col1)
        render_questions(st.container())
    with col2:
        calendar_options["initialDate"] = dt
        calendar(
            events=[
                {
                    "start": datetime.combine(
                        date.fromisoformat(dt), t["start_time"]
                    ).isoformat(),
                    "end": datetime.combine(
                        date.fromisoformat(dt), t["end_time"]
                    ).isoformat(),
                    "title": t["content"],
                }
                for t in st.session_state.cur_care_plan["tasks"]
                if t["start_time"]
            ],
            options=calendar_options,
        )


@st.dialog("Invite a new carer for this care plan")
def invite_new_carer():
    st.text_input("Email", key="invited_carer_email")
    st.text_input("First name", key="invited_carer_first_name")
    st.text_input("Last name", key="invited_carer_last_name")
    st.button("Submit", on_click=add_carer_cb)
    if st.session_state.cur_care_plan["carer_status"]:
        st.rerun()


def add_carer_cb(reinvite: bool = False):
    cl = DBClient(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    carer_id = st.session_state.cur_care_plan["carer_id"]
    if st.session_state.get("carer_to_add"):
        # existing carer
        carer_id = st.session_state.carers[st.session_state.carer_to_add][0]

    if st.session_state.get("carer_to_add") or reinvite:
        carer = cl.get_user(user_id=carer_id)
        carer.user_metadata["care_plan_id"] = st.session_state.cur_care_plan["id"]
        cl.update_user_metadata(carer_id, carer.user_metadata)
        st.session_state.db_client.sign_in_with_otp(carer.email)
    else:
        # new carer
        st.session_state.db_client.sign_in_with_otp(
            st.session_state.invited_carer_email,
            st.secrets["REDIRECT_URL"],
            st.session_state.cur_care_plan["id"],
            st.session_state.invited_carer_first_name,
            st.session_state.invited_carer_last_name,
        )
        carer = cl.get_carer(st.session_state.invited_carer_email)

    name = carer.user_metadata["first_name"] + " " + carer.user_metadata["last_name"]
    if reinvite:
        st.info(f"Reinvite sent to carer {name}")
    else:
        st.info(f"Invite sent to carer {name}")
        st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
            st.session_state.cur_care_plan["id"],
            carer_id=carer.id,
            carer_status=Carer_Status.INVITED,
        )


def add_carer():
    st.info("Add an existing carer or invite a new carer")
    carer_ids = st.session_state.db_client.get_carer_ids(st.session_state.user.id)
    cl = DBClient(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    carer_users = [cl.get_user(user_id=c) for c in carer_ids]
    st.session_state["carers"] = {
        f"{c.user_metadata["first_name"]} {c.user_metadata["last_name"]}": (
            c.id,
            c.email,
        )
        for c in carer_users
    }

    col1, col2 = st.columns(2)
    with col1:
        if st.session_state.carers:
            st.selectbox(
                "Existing carers",
                st.session_state.carers.keys(),
                index=None,
                key="carer_to_add",
                on_change=add_carer_cb,
            )
        else:
            st.error("No existing carers found")
    with col2:
        if st.button("Invite a new carer", type="primary"):
            invite_new_carer()


def create_care_plan():
    cur_care_plan = st.session_state.get("cur_care_plan")
    if cur_care_plan and date.fromisoformat(cur_care_plan["date"]) < date.today():
        del st.session_state["cur_care_plan"]
    if not st.session_state.get("cur_care_plan"):
        st.date_input("Date", value=None, min_value=date.today(), key="date")
        if not st.session_state.date:
            return
        st.session_state["cur_care_plan"] = st.session_state.db_client.create_care_plan(
            guardian_id=st.session_state.user.id, date=st.session_state.date
        )
    render_care_plan()


def care_plans():
    care_plans = st.session_state.db_client.get_care_plans(st.session_state.user.id)
    care_plans = {cp["date"]: cp for cp in care_plans}
    sorted_dates = sorted(list(care_plans.keys()), reverse=True)
    if care_plans:
        dt = st.sidebar.selectbox(
            "Existing care plans",
            sorted_dates,
        )
        st.session_state["cur_care_plan"] = care_plans[dt]
        render_care_plan()
    else:
        st.error("No existing care plans found")


def main():

    st.set_page_config(
        page_title="Relait", page_icon=":partner_exchange:", layout="wide"
    )
    init_connection()

    if st.session_state.get("user"):
        role = Role(st.session_state.user.user_metadata["role"])
        if role == Role.GUARDIAN:
            pg = st.navigation(
                [
                    st.Page(
                        create_care_plan,
                        title="Create Care Plan",
                        icon=":material/add_notes:",
                    ),
                    st.Page(
                        care_plans,
                        title="Care Plans",
                        icon=":material/mic:",
                        default=True,
                    ),
                ]
            )
            pg.run()
        else:
            rerender_care_plan()
    elif "reset_password" in st.query_params:
        fragment = get_fragment()
        if fragment:
            acces_token = (fragment.split("access_token=")[1]).split("&")[0]
            payload = jwt.decode(acces_token, options={"verify_signature": False})
            reset_password(payload["email"], payload["sub"])
    elif "add_carer" in st.query_params:
        fragment = get_fragment()
        if fragment:
            acces_token = (fragment.split("access_token=")[1]).split("&")[0]
            payload = jwt.decode(acces_token, options={"verify_signature": False})
            user_id = payload["sub"]
            care_plan_id = payload["user_metadata"]["care_plan_id"]
            st.session_state["cur_care_plan"] = (
                st.session_state.db_client.get_care_plan(care_plan_id)
            )
            if (
                st.session_state["cur_care_plan"]["carer_id"] != user_id
                or st.session_state["cur_care_plan"]["carer_status"]
                != Carer_Status.ACCEPTED
            ):
                st.session_state["cur_care_plan"] = (
                    st.session_state.db_client.update_care_plan(
                        care_plan_id,
                        carer_id=user_id,
                        carer_status=Carer_Status.ACCEPTED,
                    )
                )
            st.session_state["user"] = st.session_state.db_client.get_user(
                jwt=acces_token
            )
            st.rerun()
    else:
        register_login()


if __name__ == "__main__":
    main()
