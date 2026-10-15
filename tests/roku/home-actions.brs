sub Main()
    m.inSearch = false
    episode = {id:42,kind:"episode",season_number:2,episode_number:3,resume_position:125,duration:1300}
    show = {id:"show-test",kind:"show",resume_episode:episode}
    check(HomeResumeTarget(show).id = 42, "Series resume resolves to the exact episode")
    nextShow = {id:"show-next",title:"Show",kind:"show",continue_watching:true,
        resume_episode:{id:43,season_number:2,episode_number:4,resume_position:0,duration:1300}}
    check(HomeResumeTarget(nextShow).id = 43, "Completed episode advances directly to the next episode")
    check(HomeActionLabel(nextShow) = "▶  Next Episode", "Unstarted continuation has a clear action")
    check(BuildHomeRows([nextShow])[0].key = "continue", "Series stays on Continue Watching at zero next-episode progress")
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
    originalItem = {homeRowKey:"continue",movieData:{id:9,title:"Movie"},progress:0}
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
    continuing = {id:"continue",children:[{id:"old",homeRowKey:"continue",movieData:{id:9,kind:"movie",resume_position:120,duration:1000}}],GetChildCount:childCount,GetChild:childAt,RemoveChild:removeNode}
    allRow = {id:"all",children:[{id:"keep",homeRowKey:"all",movieData:{id:9}}],GetChildCount:childCount,GetChild:childAt}
    m.rows = {content:{children:[continuing,allRow],GetChildCount:childCount,GetChild:childAt,RemoveChild:removeNode},CallFunc:recordAnchor}
    m.search = {CallFunc:recordRefresh}
    m.hero = {CallFunc:recordRefresh}
    previousTitle = m.top.titleRequested
    updateCachedMovies([{id:9,kind:"movie",title:"Movie",completed:true,resume_position:0,duration:1000}])
    check(m.rows.content.GetChildCount() = 1 and m.rows.content.GetChild(0).id = "all", "Completed movie and empty Continue Watching row are removed")
    check(m.allRow = 0, "Movies navigation is corrected when a preceding shelf disappears")
    check(m.rows.restored.id = 9 and m.top.titleRequested = previousTitle, "Focus anchor is restored without reopening a title")
    seriesNode = {id:"series-card",homeRowKey:"continue",movieData:show,progress:0}
    shelf = {children:[seriesNode],GetChildCount:childCount,GetChild:childAt}
    m.rows = {content:{children:[shelf],GetChildCount:childCount,GetChild:childAt}}
    nextShow.id = show.id
    updateCachedMovies([nextShow])
    check(m.rows.content.GetChildCount() = 1, "Completed episode does not remove a continuing series")
    check(HomeResumeTarget(seriesNode.movieData).id = 43, "Background update advances the card to the next episode")
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

sub removeNode(node as object)
    for i = 0 to m.children.Count() - 1
        if m.children[i].id = node.id
            m.children.Delete(i)
            return
        end if
    end for
end sub
function recordAnchor(name as string, anchor = invalid as dynamic) as dynamic
    if name = "captureFocus" then return {row:1,column:0,rowKey:"all",id:9}
    m.restored = anchor
    return invalid
end function
