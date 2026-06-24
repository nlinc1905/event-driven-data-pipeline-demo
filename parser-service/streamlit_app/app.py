import tempfile

import streamlit as st

from pdf_reader import extract_pdf


st.title("PDF Parser Testing App")


@st.cache_data
def parse_pdf(pdf_bytes: bytes):
    """
    Save the uploaded PDF bytes to a temporary file, then call the extract_pdf function to parse it.
    Return the extracted text and metadata.
    """
    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as tmp:
        tmp.write(pdf_bytes)
        pdf_path = tmp.name

    return extract_pdf(pdf_path)


uploaded_file = st.file_uploader(
    "Upload PDF",
    type=["pdf"]
)

if uploaded_file:

    # Parse the PDF and display the results
    with st.spinner("Parsing PDF..."):
        result = parse_pdf(uploaded_file.read())

    # Display the JSON and Markdown results in tabs
    tab1, tab2 = st.tabs(
        ["JSON", "Markdown"]
    )

    with tab1:
        with st.container(height=600):
            st.json(result)

    with tab2:
        with st.container(height=600):
            st.markdown(result["full_markdown"])

    st.download_button(
        label="Download Markdown",
        data=result["full_markdown"],
        file_name="output.md",
        mime="text/markdown",
    )
