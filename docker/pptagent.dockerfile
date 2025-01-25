FROM forceless/pptagent:latest
ENV http_proxy=""
ENV https_proxy=""
COPY docker_launch.sh /PPTAgent/docker_launch.sh
RUN chmod +x /PPTAgent/docker_launch.sh
CMD ["/bin/bash", "/PPTAgent/docker_launch.sh"]
