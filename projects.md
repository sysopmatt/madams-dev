---
layout: page
title: Project Portfolio
subtitle: Selected professional and personal projects
---

Here are some of the key projects I've worked on:

<div class="projects-list">
{% assign sorted_projects = site.projects | sort: 'sort_date' | reverse %}
{% for project in sorted_projects %}
  <div class="project-item">
    <h2><a href="{{ project.url | relative_url }}">{{ project.title }}</a></h2>
    {% if project.subtitle %}
      <p><em>{{ project.subtitle }}</em></p>
    {% endif %}
    <p>
      <strong>Role:</strong> {{ project.role }} | 
      <strong>Dates:</strong> {{ project.dates }} | 
      <strong>Status:</strong> {{ project.status }}
    </p>
    {% if project.technologies %}
      <p><strong>Technologies:</strong> {{ project.technologies }}</p>
    {% endif %}
    <div>
      {{ project.description | markdownify }}
    </div>
    <hr style="margin-top: 2em; margin-bottom: 2em;">
  </div>
{% endfor %}
</div>

<!-- Basic styling suggestion (add to your site's CSS if desired) -->
<!--
<style>
.projects-list .project-item {
  margin-bottom: 2.5em;
}
.projects-list h2 {
  margin-bottom: 0.25em;
}
.projects-list h2 a {
  color: inherit; /* Or your desired link color */
}
.projects-list p {
  margin-top: 0.5em;
  margin-bottom: 0.5em;
}
</style>
--> 