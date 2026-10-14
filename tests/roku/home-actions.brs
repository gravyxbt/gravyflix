sub Main()
    m.inSearch = false
    episode = {id:42,kind:"episode",season_number:2,episode_number:3,resume_position:125,duration:1300}
    show = {id:"show-test",kind:"show",resume_episode:episode}
    check(HomeResumeTarget(show).id = 42, "Series resume resolves to the exact episode")
    check(HomeActionLabel(show) = "▶  Resume", "Series hero says Resume")
    check(HomeActionLabel({kind:"show"}) = "Episodes", "Unwatched series opens its browser")
    check(HomeResumeTarget({kind:"show"}) = invalid, "No fabricated episode when progress is missing")
    check(HomeActionLabel({id:9,resume_position:120,duration:3600}) = "▶  Resume", "Movie resume action")
    check(HomeActionLabel({id:9}) = "▶  Play", "Unwatched movie action")
    check(HomeResumeTarget({kind:"show",resume_episode:{id:3,season_number:0,resume_position:120}}) = invalid, "Extras cannot be the series resume target")
    check(HomeResumeTarget({id:4,resume_position:125,duration:1300,completed:true}) = invalid, "Completed item is not resumable")
    check(HomeResumeTarget({id:4,resume_position:1290,duration:1300}) = invalid, "Near-complete item is not resumable")
    m.rows = {selectedItem:{homeRowKey:"continue",movieData:show}}
    m.top = {titleRequested:0,playRequested:0}
    onMovieSelected()
    check(m.top.playRequested = 1 and m.top.titleRequested = 0, "Continue Watching emits only an explicit play command")
    check(m.top.playMovie.resume_episode.id = 42, "Continue Watching OK publishes direct playback")
    check(m.top.selectedMovie = invalid, "Continue Watching bypasses season selection")
    m.rows.selectedItem.homeRowKey = "shows"
    m.top = {titleRequested:0,playRequested:0}
    onMovieSelected()
    check(m.top.titleRequested = 1 and m.top.playRequested = 0, "Regular selection emits only a title command")
    check(m.top.selectedMovie.kind = "show", "TV Shows shelf keeps normal season browsing")
    check(m.top.playMovie = invalid, "Normal browsing does not autoplay")
    m.rows.selectedItem = {homeRowKey:"continue",movieData:{kind:"show"}}
    m.top = {titleRequested:0,playRequested:0}
    onMovieSelected()
    check(m.top.selectedMovie.kind = "show", "Missing resume data falls back safely to browsing")
    m.nav = {activated:"shows"}
    m.top.statusText = ""
    m.showsRow = 2
    m.rows = {CallFunc:recordJump}
    onNavigation()
    check(m.rows.lastRow = 2, "Shows navigation targets the TV Shows shelf")
    check(m.nav.selectedTab = "shows", "Selected navigation matches the Shows shelf")
    m.showsRow = -1
    m.rows.lastRow = -99
    m.notice = {}
    m.noticeTimer = {}
    onNavigation()
    check(m.rows.lastRow = -99, "Empty Shows library does not jump to an invalid shelf")
    check(m.notice.text = "No TV shows in your library yet.", "Empty Shows library explains what happened")
    originalItem = {movieData:{id:9,title:"Movie"},progress:0}
    root = {children:[{children:[originalItem],GetChildCount:childCount,GetChild:childAt}],GetChildCount:childCount,GetChild:childAt}
    m.rows = {content:root,focusedItem:originalItem}
    m.search = {CallFunc:recordRefresh}
    m.hero = {CallFunc:recordRefresh}
    beforeTitleRequest = m.top.titleRequested
    beforePlayRequest = m.top.playRequested
    updateCachedMovies([{id:9,title:"Movie",resume_position:120,duration:1000}])
    check(m.rows.content.GetChild(0).GetChild(0).progress = 0.12, "Progress changes in place")
    check(m.rows.focusedItem.movieData.resume_position = 120, "Focused card receives current resume position")
    check(m.top.titleRequested = beforeTitleRequest and m.top.playRequested = beforePlayRequest, "Delayed cache update cannot emit navigation commands")
    check(m.hero.called = "refreshAction", "Hero resume label updates without reloading artwork")
    m.updatingCache = true
    m.rows.selectedItem = {homeRowKey:"all",movieData:{id:9}}
    onMovieSelected()
    check(m.top.titleRequested = beforeTitleRequest, "Reentrant selection notification during cache patch is ignored")
    m.updatingCache = false
    onMovieSelected()
    check(m.top.titleRequested = beforeTitleRequest + 1, "Selecting the same title again still works")
    m.hasMovies = true
    m.top.statusText = ""
    m.inSearch = true
    m.search = {visible:true,selectedMovie:{id:9},CallFunc:recordRefresh}
    focusHome()
    check(m.search.called = "focusSearch", "Back to library restores Search instead of the home shelves")
    m.nav.activated = "search"
    m.hero = {visible:true}
    m.rows = {visible:true}
    enterSearch()
    check(m.search.visible and not m.rows.visible and not m.hero.visible, "Search replaces the browsing area")
    previousTitle = m.top.titleRequested
    onSearchSelected()
    check(m.top.titleRequested = previousTitle + 1 and m.top.selectedMovie.id = 9, "Search opens the existing title page with an explicit command")
    print "PASS: Home resume actions"
end sub

sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub

sub recordJump(name as string, row as integer)
    m.lastRow = row
end sub

function childCount() as integer
    return m.children.Count()
end function
function childAt(index as integer) as object
    return m.children[index]
end function
sub recordRefresh(name as string, data = invalid as dynamic)
    m.called = name
end sub
