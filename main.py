import streamlit as st
from store import (
    DBClient,
    Role,
    Caregiver_Status,
    CarePlan,
    Question,
    Task,
    CaregiverNote,
)
from datetime import date, datetime, time
from streamlit_calendar import calendar
from gotrue.errors import AuthApiError
from streamlit_url_fragment import get_fragment
import jwt
from streamlit_extras.stylable_container import stylable_container
from chatbot import generate_tasks_from_audio, generate_answer_from_audio
from utils import add_time, get_diff_time

TASKS_PLACEHOLDER = "No tasks yet!"
QUESTIONS_PLACEHOLDER = "No questions yet!"

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
    cp: CarePlan = st.session_state.cur_care_plan
    if st.session_state.question_list_changed["deleted_rows"]:
        for r in st.session_state.question_list_changed["deleted_rows"]:
            del cp.questions[r]
        cp = st.session_state.db_client.update_care_plan(cp.id, questions=cp.questions)

    if st.session_state.question_list_changed["edited_rows"]:
        for r, edit in st.session_state.question_list_changed["edited_rows"].items():
            if "question" in edit and QUESTIONS_PLACEHOLDER not in edit["question"]:
                cp.questions[r].question = edit["question"]
            if "answer" in edit:
                cp.questions[r].answer = edit["answer"]
            cp.questions[r].updated_at = datetime.now()
        cp = st.session_state.db_client.update_care_plan(cp.id, questions=cp.questions)

    if st.session_state.question_list_changed["added_rows"]:
        added = [
            Question(r["question"], "")
            for r in st.session_state.question_list_changed["added_rows"]
            if r.get("question")
        ]
        cp.questions.extend(added)
        cp = st.session_state.db_client.update_care_plan(cp.id, questions=cp.questions)

    st.session_state.cur_care_plan = cp


def task_list_changed():
    cp: CarePlan = st.session_state.cur_care_plan
    if st.session_state.task_list_changed["deleted_rows"]:
        for r in st.session_state.task_list_changed["deleted_rows"]:
            del cp.tasks[r]
        cp = st.session_state.db_client.update_care_plan(cp.id, tasks=cp.tasks)

    if st.session_state.task_list_changed["edited_rows"]:
        for r, edit in st.session_state.task_list_changed["edited_rows"].items():
            existing_duration = None
            if "content" in edit and TASKS_PLACEHOLDER not in edit["content"]:
                cp.tasks[r].content = edit["content"]
            if "status" in edit:
                cp.tasks[r].status = edit["status"]
            if "start_time" in edit:
                if cp.tasks[r].start_time and cp.tasks[r].end_time:
                    existing_duration = get_diff_time(
                        cp.tasks[r].start_time, cp.tasks[r].end_time
                    )
                start_time = time.fromisoformat(edit["start_time"])
                if start_time.minute > 30:
                    start_time = start_time.replace(minute=30, second=0)
                elif start_time.minute < 30:
                    start_time = start_time.replace(minute=0, second=0)
                cp.tasks[r].start_time = start_time
                if existing_duration:
                    cp.tasks[r].end_time = add_time(
                        start_time, existing_duration[0], existing_duration[1]
                    )
                else:
                    cp.tasks[r].end_time = add_time(start_time, 0, 30)

            if "end_time" in edit:
                cp.tasks[r].end_time = time.fromisoformat(edit["end_time"])
            cp.tasks[r].updated_at = datetime.now()

        cp = st.session_state.db_client.update_care_plan(cp.id, tasks=cp.tasks)

    if st.session_state.task_list_changed["added_rows"]:
        added = [
            Task(
                r["content"],
                (
                    time.fromisoformat(r.get("start_time"))
                    if r.get("start_time")
                    else None
                ),
                time.fromisoformat(r.get("end_time")) if r.get("end_time") else None,
            )
            for r in st.session_state.task_list_changed["added_rows"]
            if r.get("content")
        ]
        cp.tasks.extend(added)
        cp = st.session_state.db_client.update_care_plan(cp.id, tasks=cp.tasks)

    st.session_state.cur_care_plan = cp


def render_caregiver_status(container):
    cp: CarePlan = st.session_state.cur_care_plan
    caregiver_df = []
    for cg in cp.caregivers:
        caregiver = DBClient(
            st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
        ).get_user(user_id=cg.id)
        name = (
            caregiver.user_metadata["first_name"]
            + " "
            + caregiver.user_metadata["last_name"]
        )
        caregiver_df.append(
            {
                "name": name,
                "invitation status": cg.status.value,
                "reinvite?": (False if cg.status == Caregiver_Status.INVITED else ""),
                "email": caregiver.email,
            }
        )

    if caregiver_df:
        container.data_editor(
            caregiver_df,
            hide_index=True,
            use_container_width=True,
            column_order=["name", "invitation status", "reinvite?"],
            disabled=["name", "invitation status"],
            column_config={"reinvite?": st.column_config.CheckboxColumn()},
            on_change=caregiver_reinvite_cb,
            key="caregiver_reinvite",
            args=[caregiver_df],
        )
    add_caregiver(
        container,
        caregiver_ids_accepted=[
            cg.id for cg in cp.caregivers if cg.status == Caregiver_Status.ACCEPTED
        ],
    )


def caregiver_reinvite_cb(caregiver_df: list[dict]):
    for r, d in st.session_state.caregiver_reinvite["edited_rows"].items():
        if d.get("reinvite?"):
            try:
                st.session_state.db_client.sign_in_with_otp(
                    caregiver_df[r]["email"], st.secrets["REDIRECT_URL"]
                )
            except AuthApiError as e:
                st.error(e)


def delete_plan_cb():
    cp: CarePlan = st.session_state.get("cur_care_plan")
    if not cp:
        return
    st.session_state.db_client.delete_care_plan(cp.id)
    st.session_state.pop("cur_care_plan", None)
    st.session_state.pop("date", None)


@st.fragment(run_every="5s")
def refresh_care_plan(render: bool = False):
    cp: CarePlan = st.session_state.get("cur_care_plan")
    if not cp:
        if render:
            st.error("No care plan found")
        return
    st.session_state.cur_care_plan = st.session_state.db_client.get_care_plan(cp.id)
    if render:
        render_care_plan()


def render_tasks(disabled_columns: list[str], container):
    cp: CarePlan = st.session_state.cur_care_plan
    container.subheader("Tasks")
    container.data_editor(
        (
            [t.serialize_to_db(serialize_time=False) for t in cp.tasks]
            if cp.tasks
            else [{"content": TASKS_PLACEHOLDER}]
        ),
        column_config={
            "status": st.column_config.CheckboxColumn(),
            "start_time": st.column_config.TimeColumn(step=1800),
            "end_time": st.column_config.TimeColumn(step=1800),
        },
        column_order=("content", "start_time", "end_time", "status"),
        disabled=disabled_columns,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key="task_list_changed",
        on_change=task_list_changed,
    )


def caregiver_note_cb():
    if not st.session_state.caregiver_note:
        return
    cp: CarePlan = st.session_state.cur_care_plan
    idx = [cg.id for cg in cp.caregivers].index(st.session_state.user.id)
    cp.caregivers[idx].notes.append(CaregiverNote(st.session_state.caregiver_note))
    st.session_state.db_client.update_caregiver_notes(
        cp.id, st.session_state.user.id, cp.caregivers[idx].notes
    )


def render_caregiver_notes(container, input: bool = False):
    cp: CarePlan = st.session_state.cur_care_plan
    if cp.caregiver_notes:
        container.subheader("Caregiver Notes")
    with container:
        for note, name in cp.caregiver_notes:
            with st.chat_message("user"):
                st.write(f"{name} ({note.created_at.strftime("%H:%M")}): {note.note}")
        if input:
            st.chat_input(
                placeholder="Add a note",
                key="caregiver_note",
                on_submit=caregiver_note_cb,
            )


def render_questions(container):
    cp: CarePlan = st.session_state.cur_care_plan
    container.subheader("Questions")
    if cp.date < date.today():
        container.dataframe(
            (
                [q.serialize_to_db() for q in cp.questions]
                if cp.questions
                else [{"question": QUESTIONS_PLACEHOLDER}]
            ),
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
            (
                [q.serialize_to_db() for q in cp.questions]
                if cp.questions
                else [{"question": QUESTIONS_PLACEHOLDER}]
            ),
            column_order=("question", "answer"),
            disabled=["answer"],
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            key="question_list_changed",
            on_change=question_list_changed,
        )
        return
    # below is caregiver logic: answered questions are shown in data editor
    # and unanswered questions are shown with audio input
    answered_questions = [q.serialize_to_db() for q in cp.questions if q.answer]
    unanswered_questions = [q.serialize_to_db() for q in cp.questions if not q.answer]
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

    cp: CarePlan = st.session_state.cur_care_plan
    st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
        cp.id, questions=answered_questions + unanswered_questions
    )


def audio_input_cb():
    audio = st.session_state.get("audio")
    if audio is None:
        return
    with st.spinner("Transcribing audio"):
        tasks, questions = generate_tasks_from_audio(audio)

    cp: CarePlan = st.session_state.cur_care_plan
    cp.tasks.extend(tasks)
    cp.questions.extend(questions)
    st.session_state.cur_care_plan = st.session_state.db_client.update_care_plan(
        cp.id, tasks=cp.tasks, questions=cp.questions
    )


def render_content(tab):
    cp: CarePlan = st.session_state.cur_care_plan
    role = Role(st.session_state.user.user_metadata["role"])
    if cp.date < date.today():
        with tab:
            col1, col2 = st.columns(2)
            render_tasks(["content", "start_time", "end_time", "status"], col1)
            render_questions(st.container())
            render_caregiver_notes(st.container())
        return
    if role == Role.GUARDIAN:
        with tab:
            st.audio_input(
                "You can always create a voice recording containing instructions and/or questions",
                on_change=audio_input_cb,
                key="audio",
            )
            col1, col2 = st.columns(2)
            render_tasks(disabled_columns=["status"], container=col1)
            render_questions(st.container())
            render_caregiver_notes(st.container())
        return

    # caregiver view
    with tab:
        col1, col2 = st.columns(2)
        render_tasks(
            disabled_columns=["content", "start_time", "end_time"], container=col1
        )
        render_questions(st.container())
        render_caregiver_notes(st.container(), input=True)


def render_task_calendar(container):
    dt = st.session_state.cur_care_plan["date"]
    with container:
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


def render_care_plan():
    cp: CarePlan = st.session_state.cur_care_plan
    role = Role(st.session_state.user.user_metadata["role"])
    if role == Role.GUARDIAN and cp.date >= date.today():
        with stylable_container(
            key="delete_care_plan",
            css_styles="""
              button{
               float: right;
              }
              """,
        ):
            st.button("Delete plan", type="primary", on_click=delete_plan_cb)

        careplan_tab, caregiver_tab = st.tabs(
            [f"Care plan for {cp.date}", "Caregivers"]
        )
        render_content(careplan_tab)
        render_caregiver_status(caregiver_tab)
    else:
        render_content(st.tabs([f"Care plan for {cp.date}"])[0])


@st.dialog("Invite a new caregiver for this care plan")
def invite_new_caregiver():
    st.text_input("Email", key="invited_caregiver_email")
    st.text_input("First name", key="invited_caregiver_first_name")
    st.text_input("Last name", key="invited_caregiver_last_name")
    st.button("Submit", on_click=add_caregiver_cb)
    if st.session_state.get("new_caregiver_accepted"):
        del st.session_state["new_caregiver_accepted"]
        st.error("This caregiver has already accepted an invite")
    if st.session_state.get("new_caregiver_invite_sent"):
        del st.session_state["new_caregiver_invite_sent"]
        st.rerun()


@st.dialog("Your invitation has expired. Please generate another invitation")
def caregiver_invites_themselves():
    st.text_input("Email", key="invited_caregiver_email")
    st.button("Submit", on_click=caregiver_invites_themselves_cb)
    if st.session_state.get("reinvite_sent"):
        st.rerun()


def caregiver_invites_themselves_cb():
    st.session_state.db_client.sign_in_with_otp(
        st.session_state.invited_caregiver_email, st.secrets["REDIRECT_URL"]
    )
    st.session_state["reinvite_sent"] = True


def add_caregiver_cb():
    cp: CarePlan = st.session_state.cur_care_plan
    cl = DBClient(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    if st.session_state.get("caregiver_to_add"):
        # existing caregiver
        caregiver_id = st.session_state.caregivers[st.session_state.caregiver_to_add][0]
        caregiver = cl.get_user(user_id=caregiver_id)
        caregiver.user_metadata["care_plan_id"] = cp.id
        cl.update_user_metadata(caregiver_id, caregiver.user_metadata)
        try:
            st.session_state.db_client.sign_in_with_otp(
                caregiver.email, st.secrets["REDIRECT_URL"]
            )
        except AuthApiError as e:
            st.error(e)
    else:
        # new caregiver, but their email might already exist in the user table
        caregiver = cl.get_caregiver_user(st.session_state.invited_caregiver_email)
        if caregiver:
            # if this caregiver has already accepted return error message and noop
            caregivers = st.session_state.db_client.get_caregivers(cp.id, caregiver.id)
            if (
                caregivers
                and Caregiver_Status(caregivers[0]["caregiver_status"])
                == Caregiver_Status.ACCEPTED
            ):
                st.session_state["new_caregiver_accepted"] = True
                return
            caregiver.user_metadata["care_plan_id"] = cp.id
            cl.update_user_metadata(caregiver.id, caregiver.user_metadata)

        st.session_state.db_client.sign_in_with_otp(
            st.session_state.invited_caregiver_email,
            st.secrets["REDIRECT_URL"],
            cp.id,
            st.session_state.invited_caregiver_first_name,
            st.session_state.invited_caregiver_last_name,
        )
        caregiver = cl.get_caregiver_user(st.session_state.invited_caregiver_email)

    name = (
        caregiver.user_metadata["first_name"]
        + " "
        + caregiver.user_metadata["last_name"]
    )
    st.session_state.db_client.create_caregiver_in_care_plan(caregiver.id, cp.id, name)
    st.session_state["new_caregiver_invite_sent"] = True


def add_caregiver(container, caregiver_ids_accepted: list[str] = []):
    container.info("Add an existing caregiver or invite a new caregiver")
    caregiver_ids = st.session_state.db_client.get_caregiver_ids_for_guardian(
        st.session_state.user.id
    )
    cl = DBClient(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    caregiver_users = []
    for c in caregiver_ids:
        if c in caregiver_ids_accepted:
            continue
        u = cl.get_user(user_id=c)
        if u:
            caregiver_users.append(u)
    st.session_state["caregivers"] = {
        f"{c.user_metadata["first_name"]} {c.user_metadata["last_name"]}": (
            c.id,
            c.email,
        )
        for c in caregiver_users
    }

    col1, col2 = container.columns(2)
    with col1:
        if st.session_state.caregivers:
            container.selectbox(
                "Existing caregivers",
                st.session_state.caregivers.keys(),
                index=None,
                key="caregiver_to_add",
                on_change=add_caregiver_cb,
            )
        else:
            container.error("No existing caregivers found")
    with col2:
        if container.button("Invite a new caregiver", type="primary"):
            invite_new_caregiver()


def create_care_plan():
    cur_care_plan: CarePlan = st.session_state.get("cur_care_plan")
    if cur_care_plan and cur_care_plan.date < date.today():
        del st.session_state["cur_care_plan"]
        cur_care_plan = None
    if not cur_care_plan:
        st.date_input("Date", value=None, min_value=date.today(), key="date")
        if not st.session_state.date:
            return
        st.session_state["cur_care_plan"] = st.session_state.db_client.create_care_plan(
            guardian_id=st.session_state.user.id, date=st.session_state.date
        )
    render_care_plan()


def care_plans():
    care_plans: list[CarePlan] = st.session_state.db_client.get_care_plans(
        st.session_state.user.id
    )
    care_plans = {cp.date: cp for cp in care_plans}
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
            refresh_care_plan()
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
            refresh_care_plan(render=True)
    elif "reset_password" in st.query_params:
        fragment = get_fragment()
        if fragment:
            acces_token = (fragment.split("access_token=")[1]).split("&")[0]
            payload = jwt.decode(acces_token, options={"verify_signature": False})
            reset_password(payload["email"], payload["sub"])
    elif "add_caregiver" in st.query_params:
        fragment = get_fragment()
        if fragment:
            fields = fragment.split("access_token=")
            if len(fields) < 2:
                # access token could not be found. Need to regenerate otp
                if not st.session_state.get("reinvite_sent"):
                    caregiver_invites_themselves()
                return
            acces_token = fields[1].split("&")[0]
            payload = jwt.decode(acces_token, options={"verify_signature": False})
            user_id = payload["sub"]
            care_plan_id = payload["user_metadata"]["care_plan_id"]
            st.session_state["cur_care_plan"] = (
                st.session_state.db_client.get_care_plan(care_plan_id)
            )
            if not st.session_state["cur_care_plan"]:
                st.error("No care plan found")
                return
            st.session_state["user"] = st.session_state.db_client.get_user(
                jwt=acces_token
            )
            st.session_state.db_client.update_caregiver_status(
                care_plan_id, user_id, Caregiver_Status.ACCEPTED
            )
            st.rerun()
    else:
        register_login()


if __name__ == "__main__":
    main()
