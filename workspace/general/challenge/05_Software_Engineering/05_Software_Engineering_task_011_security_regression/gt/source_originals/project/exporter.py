import csv,io

def render_csv(rows,columns):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(columns)
    for row in rows:writer.writerow([row[column] for column in columns])
    return stream.getvalue()
