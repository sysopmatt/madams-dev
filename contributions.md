---
layout: page
title: Open Source Contributions
subtitle: Contributions to various open source projects
---

Here are some of the contributions I've made to open source projects:

<ul class="contributions-list">
{% assign sorted_contributions = site.contributions | sort: 'date' | reverse %}
{% for contribution in sorted_contributions %}
  <li>
    <h3><a href="{{ contribution.contribution_url }}" target="_blank" rel="noopener noreferrer">{{ contribution.title }}</a></h3>
    <p>
      <strong>Project:</strong> <a href="{{ contribution.project_url }}" target="_blank" rel="noopener noreferrer">{{ contribution.project }}</a> <br>
      <strong>Type:</strong> {{ contribution.contribution_type }} | 
      <strong>Status:</strong> {{ contribution.status }} | 
      <strong>Date:</strong> {{ contribution.date | date: "%Y-%m-%d" }}
    </p>
    <p>{{ contribution.description | markdownify }}</p>
    {% if contribution.tags.size > 0 %}
      <p><em>Tags: {{ contribution.tags | join: ", " }}</em></p>
    {% endif %}
    <hr>
  </li>
{% endfor %}
</ul>

<!-- Basic styling suggestion (add to your site's CSS if desired) -->
<!--
<style>
.contributions-list {
  list-style: none;
  padding-left: 0;
}
.contributions-list li {
  margin-bottom: 2em;
}
.contributions-list h3 {
  margin-bottom: 0.5em;
}
.contributions-list p {
  margin-top: 0.5em;
  margin-bottom: 0.5em;
}
</style>
--> 