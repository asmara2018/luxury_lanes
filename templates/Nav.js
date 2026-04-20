// nav.js - Shared navigation for Luxury Lanes
// This file is included by every page so the sidebar order is always identical.
// Each page calls buildNav('PageFilename.html') to mark its own link as current.

function buildNavFromJS(currentPage) {

    // MASTER nav list - order never changes, role filter controls visibility
    var allLinks = [
        { page: 'Dashboard.html',     label: 'Dashboard',     roles: ['Guest', 'Staff', 'Subcontractor', 'Manager'] },
        { page: 'ReportFault.html',   label: 'Report Fault',  roles: ['Guest', 'Staff', 'Manager'] },
        { page: 'AssignJob.html',     label: 'Assign Jobs',   roles: ['Staff', 'Manager'] },
        { page: 'ViewJobs.html',      label: 'My Jobs',       roles: ['Subcontractor'] },
        { page: 'View Requests.html', label: 'View Requests', roles: ['Guest', 'Staff', 'Manager'] },
        { page: 'Analytics.html',     label: 'Analytics',     roles: ['Manager'] },
        { page: 'Notifications.html', label: 'Notifications', roles: ['Guest', 'Staff', 'Subcontractor', 'Manager'] },
        { page: 'Feedback.html',      label: 'Feedback',      roles: ['Guest', 'Staff', 'Subcontractor', 'Manager'] }
    ];

    var role = localStorage.getItem('role') || '';
    var nav  = document.getElementById('navLinks');

    if (!nav) return;

    nav.innerHTML = '';

    for (var i = 0; i < allLinks.length; i++) {
        var link = allLinks[i];
        if (link.roles.indexOf(role) === -1) continue;

        var a = document.createElement('a');
        a.href      = link.page;
        a.textContent = link.label;

        // highlight the current page
        if (link.page === currentPage) {
            a.className = 'current';
        }

        nav.appendChild(a);
    }
}