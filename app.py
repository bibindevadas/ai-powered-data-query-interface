
import time

from google.cloud import bigquery
import streamlit as st
from vertexai.generative_models import FunctionDeclaration, GenerativeModel, Part, Tool

BIGQUERY_DATASET_ID = "airline_bookings"

list_datasets_func = FunctionDeclaration(
    name="list_datasets",
    description="Get a list of datasets that will help answer the user's question",
    parameters={
        "type": "object",
        "properties": {},
    },
)

list_tables_func = FunctionDeclaration(
    name="list_tables",
    description="List tables in a dataset that will help answer the user's question",
    parameters={
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "Dataset ID to fetch tables from.",
            }
        },
        "required": [
            "dataset_id",
        ],
    },
)

get_table_func = FunctionDeclaration(
    name="get_table",
    description="Get information about a table, including the description, schema, and number of rows that will help answer the user's question. Always use the fully qualified dataset and table names.",
    parameters={
        "type": "object",
        "properties": {
            "table_id": {
                "type": "string",
                "description": "Fully qualified ID of the table to get information about",
            }
        },
        "required": [
            "table_id",
        ],
    },
)

sql_query_func = FunctionDeclaration(
    name="sql_query",
    description="Get information from data in BigQuery using SQL queries",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SQL query on a single line that will help give quantitative answers to the user's question when run on a BigQuery dataset and table. In the SQL query, always use the fully qualified dataset and table names.",
            }
        },
        "required": [
            "query",
        ],
    },
)

sql_query_tool = Tool(
    function_declarations=[
        list_datasets_func,
        list_tables_func,
        get_table_func,
        sql_query_func,
    ],
)

model = GenerativeModel(
    "gemini-1.5-pro",
    generation_config={"temperature": 0},
    tools=[sql_query_tool],
)

st.set_page_config(
    page_title="AI Powered Data Query Interface",
    page_icon="vertex-ai.png",
    layout="wide",
)

col1, col2 = st.columns([8, 1])
with col1:
    st.title("AI Powered Data Querying")
with col2:
    st.image("vertex-ai.png")

st.subheader("Powered by Function Calling in Gemini")


with st.expander("Sample prompts", expanded=True):
    st.write(
        """
        - What kind of information is in this database?
        - Which states have the highest number of frequent flyers?
        - Show the average ticket price for international flights grouped by airline.
        - How many customers booked more than 3 times in the last 3 months?
        - Compare ticket prices for business and economy classes.
    """
    )
    

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"].replace("$", r"\$"))  # noqa: W605
        try:
            with st.expander("Function calls, parameters, and responses"):
                st.markdown(message["backend_details"])
        except KeyError:
            pass

if prompt := st.chat_input("Ask me about information in the database..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        chat = model.start_chat()
        client = bigquery.Client()

        prompt += """
                        You are an expert data assistant trained to query, analyze, and summarize data from BigQuery. Your task is to:
                        1. Understand the user's query related to airline bookings and customer data.
                        2. Generate SQL queries to retrieve precise information, execute the queries and return the results, along with any insights or trends, in plain language.

                        #### Dataset Details:
                        **Dataset Name**: `airline_bookings`
                        **Tables**:
                        1. `customer_profiles`: CustomerID, AgeGroup, Gender, FrequentFlyer, State, City.
                        2. `airline_bookings`: BookingID, CustomerID, Airline, Destination, BookingDate, FlightType, TicketPrice, Class, BookingChannel, AffinityIndex.

                        #### Instructions:
              
                        - Execute the SQL queries and return results in a user-friendly format, e.g., tables, lists, or visualizations.
                        - Offer a concise summary of the results with key insights (e.g., trends, top values, outliers).
                        - If a query involves trends, calculate totals or averages grouped by time (e.g., months, years).
                        - For queries about specific subsets of data (e.g., "frequent flyers"), include appropriate filters and return results.

                        #### Examples:
                        1. **Query**: "What are the top 10 cities by total revenue from domestic flights?"
                           - SQL: `SELECT City, SUM(TicketPrice) AS TotalRevenue FROM \`airline_bookings.airline_bookings\` WHERE FlightType = 'Domestic' GROUP BY City ORDER BY TotalRevenue DESC LIMIT 10;`
                           - Result: Return the top 10 cities as a table with "City" and "Total Revenue" columns.


                        #### User Query:
                        {user_query}

                        #### Expectations:
                        - Respond to the query with the SQL query used, the resulting data (or error details if the query fails), and insights.
                        - If the query requires advanced analysis or visualization, suggest the most relevant visualization (e.g., bar chart, trend line, table).
                        - If additional clarification is needed, ask follow-up questions to better understand the user's intent.
                        
                        Important Notes:
                        1. The following columns exist in **both tables**: `AgeGroup`, `Gender`, `FrequentFlyer`, `State`, and `City`. Always qualify these column names with the table name or alias in the query.
                               - Use `cp` for `customer_profiles` (e.g., `cp.State`, `cp.AgeGroup`).
                               - Use `abd` for `airline_bookings_data` (e.g., `abd.State`, `abd.AgeGroup`).
                        2. When joining the tables, you can use `CustomerID` as the key for the join.
                        3. Ensure the generated SQL queries are free of ambiguity and fully qualify columns, especially in SELECT, WHERE, GROUP BY, and ORDER BY clauses.
                        4. For GROUP BY queries, explicitly use the fully qualified column name in the GROUP BY clause.
            

            """

        try:
            response = chat.send_message(prompt)
            response = response.candidates[0].content.parts[0]

            print(response)

            api_requests_and_responses = []
            backend_details = ""

            function_calling_in_process = True
            while function_calling_in_process:
                try:
                    params = {}
                    for key, value in response.function_call.args.items():
                        params[key] = value

                    print(response.function_call.name)
                    print(params)

                    if response.function_call.name == "list_datasets":
                        api_response = client.list_datasets()
                        api_response = BIGQUERY_DATASET_ID
                        api_requests_and_responses.append(
                            [response.function_call.name, params, api_response]
                        )

                    if response.function_call.name == "list_tables":
                        api_response = client.list_tables(params["dataset_id"])
                        api_response = str([table.table_id for table in api_response])
                        api_requests_and_responses.append(
                            [response.function_call.name, params, api_response]
                        )

                    if response.function_call.name == "get_table":
                        api_response = client.get_table(params["table_id"])
                        api_response = api_response.to_api_repr()
                        api_requests_and_responses.append(
                            [
                                response.function_call.name,
                                params,
                                [
                                    str(api_response.get("description", "")),
                                    str(
                                        [
                                            column["name"]
                                            for column in api_response["schema"][
                                                "fields"
                                            ]
                                        ]
                                    ),
                                ],
                            ]
                        )
                        api_response = str(api_response)

                    if response.function_call.name == "sql_query":
                        job_config = bigquery.QueryJobConfig(
                            maximum_bytes_billed=100000000
                        )  # Data limit per query job
                        try:
                            cleaned_query = (
                                params["query"]
                                .replace("\\n", " ")
                                .replace("\n", "")
                                .replace("\\", "")
                            )
                            query_job = client.query(
                                cleaned_query, job_config=job_config
                            )
                            api_response = query_job.result()
                            api_response = str([dict(row) for row in api_response])
                            api_response = api_response.replace("\\", "").replace(
                                "\n", ""
                            )
                            api_requests_and_responses.append(
                                [response.function_call.name, params, api_response]
                            )
                        except Exception as e:
                            error_message = f"""
                            We're having trouble running this SQL query. This
                            could be due to an invalid query or the structure of
                            the data. Try rephrasing your question to help the
                            model generate a valid query. Details:

                            {str(e)}"""
                            st.error(error_message)
                            api_response = error_message
                            api_requests_and_responses.append(
                                [response.function_call.name, params, api_response]
                            )
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": error_message,
                                }
                            )

                    print(api_response)

                    response = chat.send_message(
                        Part.from_function_response(
                            name=response.function_call.name,
                            response={
                                "content": api_response,
                            },
                        ),
                    )
                    response = response.candidates[0].content.parts[0]

                    backend_details += "- Function call:\n"
                    backend_details += (
                        "   - Function name: ```"
                        + str(api_requests_and_responses[-1][0])
                        + "```"
                    )
                    backend_details += "\n\n"
                    backend_details += (
                        "   - Function parameters: ```"
                        + str(api_requests_and_responses[-1][1])
                        + "```"
                    )
                    backend_details += "\n\n"
                    backend_details += (
                        "   - API response: ```"
                        + str(api_requests_and_responses[-1][2])
                        + "```"
                    )
                    backend_details += "\n\n"
                    with message_placeholder.container():
                        st.markdown(backend_details)

                except AttributeError:
                    function_calling_in_process = False

            time.sleep(3)

            full_response = response.text
            with message_placeholder.container():
                st.markdown(full_response.replace("$", r"\$"))  # noqa: W605
                with st.expander("Function calls, parameters, and responses:"):
                    st.markdown(backend_details)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": full_response,
                    "backend_details": backend_details,
                }
            )
        except Exception as e:
            print(e)
            error_message = f"""
                Something went wrong! We encountered an unexpected error while
                trying to process your request. Please try rephrasing your
                question. Details:

                {str(e)}"""
            st.error(error_message)
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": error_message,
                }
            )