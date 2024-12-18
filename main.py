import streamlit as st
import webvtt
import base64
from openai import OpenAI, pydantic_function_tool
from pydantic import BaseModel, Field
import json
from datetime import date, datetime, timedelta
from streamlit_calendar import calendar


class Instruction(BaseModel):
    start_time: str | None = Field(
        description="Possible start time in format HH:MM AM/PM"
    )
    end_time: str | None = Field(description="Possible end time in format HH:MM AM/PM")
    content: str = Field(description="content of the instruction")


class GetInstructions(BaseModel):
    """get list of instructions in the audio input"""

    instructions: list[Instruction] = Field(description="instructions detected")


calendar_options = {
    "headerToolbar": False,
    "slotMinTime": "06:00:00",
    "slotMaxTime": "18:00:00",
    "initialView": "timeGridDay",
}


def task_list_changed():
    for r in st.session_state.task_list_changed["deleted_rows"]:
        del st.session_state.tasks[r]
    for r in st.session_state.task_list_changed["added_rows"]:
        task = {"task": r.get("task"), "status": False}
        start_time = (
            datetime.strptime(r["start_time"], "%H:%M:S")
            if r.get("start_time")
            else None
        )
        if start_time:
            start_time = start_time.replace(year=st.session_state.date.year)
            start_time = start_time.replace(month=st.session_state.date.month)
            start_time = start_time.replace(day=st.session_state.date.day)

        if "end_time" in r:
            end_time = datetime.strptime(r["end_time"], "%H:%M:S")
            end_time = end_time.replace(year=st.session_state.date.year)
            end_time = end_time.replace(month=st.session_state.date.month)
            end_time = end_time.replace(day=st.session_state.date.day)
        elif start_time:
            end_time = start_time + timedelta(minutes=30)
        else:
            end_time = None

        task["start_time"] = start_time
        task["end_time"] = end_time
        st.session_state.tasks.append(task)


def current_memo():
    tasks = st.session_state.get("tasks")
    if tasks is None:
        st.error("There is no current instructions memo. Please create one.")
        return

    col1, col2 = st.columns(2)
    col1.data_editor(
        tasks,
        column_config={
            "status": st.column_config.CheckboxColumn(),
            "start_time": st.column_config.TimeColumn(),
            "end_time": st.column_config.TimeColumn(),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key="task_list_changed",
        on_change=task_list_changed,
    )
    with col2:
        calendar(
            events=[
                {
                    "start": t["start_time"].isoformat(),
                    "end": t["end_time"].isoformat(),
                    "title": t["task"],
                }
                for t in tasks
                if t["start_time"]
            ],
            options=calendar_options,
        )


def create_memo():

    st.session_state["date"] = st.date_input(
        "Date", value=date.today(), min_value=date.today()
    )
    audio = st.audio_input("Please record a conversation")
    if not audio:
        return
    encoded_string = base64.b64encode(audio.getvalue()).decode("utf-8")
    with st.spinner("Generating Task list"):
        completion = OpenAI().chat.completions.create(
            model="gpt-4o-audio-preview",
            modalities=["text"],
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Each user input will be an audio message containing some instructions for a health aide. Each instructions might have a start time and/or an end time. Use the supplied function to parse the instructions in a list format.",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": encoded_string, "format": "wav"},
                        },
                    ],
                },
            ],
            tools=[pydantic_function_tool(GetInstructions)],
        )
    arguments = json.loads(
        completion.choices[0].message.tool_calls[0].function.arguments
    )
    instructions = GetInstructions(**arguments).instructions
    tasks = []
    for ins in instructions:
        start_time = (
            datetime.strptime(ins.start_time, "%I:%M %p") if ins.start_time else None
        )
        if start_time:
            start_time = start_time.replace(year=st.session_state.date.year)
            start_time = start_time.replace(month=st.session_state.date.month)
            start_time = start_time.replace(day=st.session_state.date.day)

        if ins.end_time:
            end_time = datetime.strptime(ins.end_time, "%I:%M %p")
            end_time = end_time.replace(year=st.session_state.date.year)
            end_time = end_time.replace(month=st.session_state.date.month)
            end_time = end_time.replace(day=st.session_state.date.day)
        elif start_time:
            end_time = start_time + timedelta(minutes=30)
        else:
            end_time = None

        tasks.append(
            {
                "task": ins.content,
                "start_time": start_time,
                "end_time": end_time,
                "status": False,
            }
        )
    st.session_state["tasks"] = tasks
    st.switch_page(st.session_state.current_memo_pg)


def main():

    st.set_page_config(
        page_title="Relait", page_icon=":partner_exchange:", layout="wide"
    )

    st.info(f"Welcome Jane Doe!")
    current_memo_pg = st.Page(
        current_memo,
        title="Current memo",
        icon=":material/mic:",
        default=True,
    )
    st.session_state["current_memo_pg"] = current_memo_pg
    pg = st.navigation(
        [
            st.Page(
                create_memo,
                title="Create memo",
                icon=":material/mic:",
            ),
            current_memo_pg,
        ]
    )
    pg.run()


if __name__ == "__main__":
    main()
