
# Use an official Python runtime as the base image
FROM python:3.8-buster

# Set the working directory in the container
WORKDIR /app

# Install ca-certificates
RUN apt-get update && apt-get install -y ca-certificates

# Upgrade pip
RUN pip install --upgrade pip

# Copy the current directory contents into the container at /app
COPY MACLv16.py /app/
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Run MACLv16.py when the container launches
CMD ["python", "MACLv16.py"]
