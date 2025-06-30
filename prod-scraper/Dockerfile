# Define custom function directory
ARG FUNCTION_DIR="/function"

# Use Playwright Python image as base
FROM mcr.microsoft.com/playwright/python:v1.52.0-noble AS build-image

# Include global arg in this stage of the build
ARG FUNCTION_DIR

# Install Python dependencies to FUNCTION_DIR
RUN pip install --root-user-action=ignore --target ${FUNCTION_DIR} \
    awslambdaric \
    playwright==1.52.0 \
    beautifulsoup4==4.12.3 \
    boto3

# Add FUNCTION_DIR/bin to PATH to ensure playwright CLI is accessible
ENV PATH="${FUNCTION_DIR}/bin:${PATH}"

# Install Playwright browsers and dependencies, ensuring playwright module is found
RUN PYTHONPATH=${FUNCTION_DIR} python -m playwright install --with-deps chromium

# Create function directory and copy files
RUN mkdir -p ${FUNCTION_DIR}
COPY lambda_function.py ${FUNCTION_DIR}/lambda_function.py
COPY . ${FUNCTION_DIR}/
# COPY seccomp_profile.json ${FUNCTION_DIR}/seccomp_profile.json

# Use a slim version of the Playwright image for the final stage
FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

# Include global arg
ARG FUNCTION_DIR
WORKDIR ${FUNCTION_DIR}

# Copy built dependencies and files from build stage
COPY --from=build-image ${FUNCTION_DIR} ${FUNCTION_DIR}

# Set PATH for the final image
ENV PATH="${FUNCTION_DIR}/bin:${PATH}"

# Set PYTHONPATH for Lambda runtime
ENV PYTHONPATH=${FUNCTION_DIR}

# Create non-root user for security (pwuser exists in Playwright image)
USER pwuser

# Set runtime interface client as default command for Lambda
ENTRYPOINT ["/usr/bin/python3", "-m", "awslambdaric"]
# Pass the name of the function handler
CMD ["lambda_function.lambda_handler"]