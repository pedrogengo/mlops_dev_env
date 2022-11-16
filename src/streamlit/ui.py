import requests
import pandas as pd
import streamlit as st

uploaded_file = st.file_uploader("Choose a CSV file to generate predictions:", type='csv')
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    x = df.values.tolist()

    r = requests.post("<YOUR CLOUD FUNCTION URL>", json={'input': x})

    if r.status_code == 200:
        df["predicted"] = r.json()['target']
        st.text(r.json()['target'])
        st.download_button(
            label="Download data as CSV",
            data=df.to_csv(index=False),
            file_name='predicted.csv',
            mime='text/csv',
        )
    else:
        st.text(r.content)