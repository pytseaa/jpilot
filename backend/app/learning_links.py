"""A curated list of learning links the team has checked by hand.

The check prompt never holds a URL: Qwen only returns a link id, and the
backend looks it up here. Any id that is not in this list is dropped, so a
made-up URL never reaches the candidate.

The team must open every URL once before the demo and again before the final
evaluation (see ticket 14). This is a small test list for now; the real 30 to
50 entries ship later.
"""

LEARNING_LINKS = [
    {"id": "sql-basics", "title": "SQL Basics", "url": "https://www.sqltutorial.org/sqlselect/"},
    {"id": "sql-advanced", "title": "Advanced SQL", "url": "https://mode.com/sql-tutorial/sql-window-functions/"},
    {"id": "python-basics", "title": "Python Basics", "url": "https://docs.python.org/3/tutorial/"},
    {"id": "python-pandas", "title": "Pandas for Data Analysis", "url": "https://pandas.pydata.org/docs/getting_started/"},
    {"id": "python-numpy", "title": "NumPy Fundamentals", "url": "https://numpy.org/doc/stable/user/absolute_beginners.html"},
    {"id": "tableau-basics", "title": "Tableau Getting Started", "url": "https://help.tableau.com/current/guides/get-started-tutorial/en-us/"},
    {"id": "powerbi-basics", "title": "Power BI Fundamentals", "url": "https://learn.microsoft.com/en-us/power-bi/fundamentals/"},
    {"id": "excel-advanced", "title": "Advanced Excel", "url": "https://support.microsoft.com/en-us/office/advanced-excel-skills"},
    {"id": "statistics", "title": "Statistics for Data Analysts", "url": "https://www.khanacademy.org/math/statistics-probability"},
    {"id": "ml-basics", "title": "Machine Learning Intro", "url": "https://developers.google.com/machine-learning/crash-course"},
    {"id": "deep-learning", "title": "Deep Learning Specialization", "url": "https://www.coursera.org/specializations/deep-learning"},
    {"id": "aws-cloud", "title": "AWS Cloud Practitioner", "url": "https://aws.amazon.com/training/learn-about/aws-cloud-practitioner/"},
    {"id": "docker-basics", "title": "Docker Getting Started", "url": "https://docs.docker.com/get-started/"},
    {"id": "kubernetes-basics", "title": "Kubernetes Basics", "url": "https://kubernetes.io/docs/tutorials/kubernetes-basics/"},
    {"id": "git-basics", "title": "Git Handbook", "url": "https://git-scm.com/book/en/v2"},
    {"id": "linux-basics", "title": "Linux Command Line", "url": "https://ubuntu.com/tutorials/command-line-for-beginners"},
    {"id": "spark-basics", "title": "Apache Spark Tutorials", "url": "https://spark.apache.org/docs/latest/quick-start.html"},
    {"id": "airflow-basics", "title": "Apache Airflow Fundamentals", "url": "https://airflow.apache.org/docs/apache-airflow/stable/tutorial/"},
    {"id": "dbt-basics", "title": "dbt Fundamentals", "url": "https://courses.getdbt.com/collections"},
    {"id": "r-basics", "title": "R for Data Science", "url": "https://r4ds.had.co.nz/"},
]

# Looked up by id when the check answer comes back. A missing id means the
# requirement still shows as a skill gap, just without a learning link.
BY_ID = {link["id"]: link for link in LEARNING_LINKS}
