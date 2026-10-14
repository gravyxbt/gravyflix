sub init()
    m.hero = m.top.FindNode("hero")
    m.rows = m.top.FindNode("rows")
    m.nav = m.top.FindNode("nav")
    m.search = m.top.FindNode("search")
    m.inSearch = false
    m.browseTab = "home"
    m.statusPanel = m.top.FindNode("statusPanel")
    m.status = m.top.FindNode("status")
    m.notice = m.top.FindNode("notice")
    m.noticeTimer = m.top.FindNode("noticeTimer")
    m.hasMovies = false
    m.updatingCache = false
    m.allRow = -1
    m.showsRow = -1
    m.rows.ObserveField("focusedItem", "onMovieFocused")
    m.rows.ObserveField("selectionRequested", "onMovieSelected")
    m.rows.ObserveField("exitUp", "focusHero")
    m.hero.ObserveField("playRequested", "onHeroPlay")
    m.hero.ObserveField("exitUp", "focusNavigation")
    m.hero.ObserveField("exitDown", "focusRows")
    m.nav.ObserveField("exitDown", "focusHero")
    m.nav.ObserveField("activated", "onNavigation")
    m.search.ObserveField("titleRequested", "onSearchSelected")
    m.search.ObserveField("exitRequested", "leaveSearch")
    m.search.ObserveField("exitUp", "focusNavigation")
    m.noticeTimer.ObserveField("fire", "clearNotice")
end sub

sub onMoviesChanged()
    movies = m.top.movies
    if movies = invalid then return
    m.search.movies = movies
    definitions = BuildHomeRows(movies)
    root = CreateObject("roSGNode", "ContentNode")
    m.allRow = -1
    m.showsRow = -1
    for each definition in definitions
        row = root.CreateChild("ContentNode")
        row.title = definition.title
        if definition.key = "all" then m.allRow = root.GetChildCount() - 1
        if definition.key = "shows" then m.showsRow = root.GetChildCount() - 1
        for each entry in definition.items
            item = row.CreateChild("MovieContent")
            item.SetFields({
                title: entry.title, description: entry.description
                metadataLine: entry.metadataLine, cardImage: entry.cardImage
                portraitArt: entry.portraitArt, heroImage: entry.heroImage
                progress: entry.progress, movieData: entry.movieData, homeRowKey: definition.key
            })
        end for
    end for
    m.hasMovies = root.GetChildCount() > 0
    m.rows.content = root
    if m.hasMovies
        m.hero.content = root.GetChild(0).GetChild(0)
        m.top.statusText = ""
        onStatus()
        m.rows.CallFunc("jumpToRow", 0)
    else
        m.top.statusText = "No movies yet." + Chr(10) + "Add movies to your library, scan it, then press OK to refresh."
    end if
end sub

sub onStatus()
    showingStatus = m.top.statusText <> ""
    m.statusPanel.visible = showingStatus
    m.status.text = m.top.statusText
    m.search.visible = not showingStatus and m.inSearch
    m.hero.visible = not showingStatus and m.hasMovies and not m.inSearch
    m.rows.visible = not showingStatus and m.hasMovies and not m.inSearch
    if showingStatus then m.top.SetFocus(true)
end sub

sub focusHome()
    if m.hasMovies and m.top.statusText = ""
        if m.inSearch then m.search.CallFunc("focusSearch") else focusRows()
    else
        m.top.SetFocus(true)
    end if
end sub

sub focusRows()
    if m.hasMovies and m.top.statusText = "" then m.rows.CallFunc("focusList")
end sub

sub focusHero()
    if not m.hasMovies or m.top.statusText <> "" then return
    if m.inSearch then m.search.CallFunc("focusSearch") else m.hero.SetFocus(true)
end sub

sub focusNavigation()
    m.nav.SetFocus(true)
end sub

sub onMovieFocused()
    item = m.rows.focusedItem
    if item <> invalid then m.hero.content = item
end sub

sub onMovieSelected()
    if m.updatingCache = true then return
    item = m.rows.selectedItem
    if item = invalid then return
    if item.homeRowKey = "continue" and HomeResumeTarget(item.movieData) <> invalid
        m.top.playMovie = item.movieData
        m.top.playRequested++
    else
        m.top.selectedMovie = item.movieData
        m.top.titleRequested++
    end if
end sub

sub onHeroPlay()
    if m.updatingCache = true then return
    if m.hero.content = invalid then return
    m.top.playMovie = m.hero.content.movieData
    m.top.playRequested++
end sub

sub onNavigation()
    if m.top.statusText <> "" then return
    if m.nav.activated <> "search" and m.inSearch then hideSearch()
    if m.nav.activated = "movies"
        if m.allRow >= 0
            m.nav.selectedTab = "movies"
            m.rows.CallFunc("jumpToRow", m.allRow)
        else
            showNotice("No movies in your library yet.")
        end if
    else if m.nav.activated = "shows"
        if m.showsRow >= 0
            m.nav.selectedTab = "shows"
            m.rows.CallFunc("jumpToRow", m.showsRow)
        else
            showNotice("No TV shows in your library yet.")
        end if
    else if m.nav.activated = "home"
        m.nav.selectedTab = "home"
        m.rows.CallFunc("jumpToRow", 0)
    else if m.nav.activated = "search"
        enterSearch()
    end if
end sub

sub enterSearch()
    if not m.inSearch then m.browseTab = m.nav.selectedTab
    m.inSearch = true
    m.nav.selectedTab = "search"
    m.hero.visible = false
    m.rows.visible = false
    m.search.visible = true
    m.search.CallFunc("focusSearch")
end sub

sub hideSearch()
    m.nav.selectedTab = m.browseTab
    m.inSearch = false
    m.search.visible = false
    m.hero.visible = m.hasMovies
    m.rows.visible = m.hasMovies
end sub

sub leaveSearch()
    hideSearch()
    m.nav.selectedTab = m.browseTab
    focusNavigation()
end sub

sub onSearchSelected()
    if not m.inSearch or not m.search.visible or m.updatingCache then return
    m.top.selectedMovie = m.search.selectedMovie
    m.top.titleRequested++
end sub

sub showNotice(message as string)
    m.notice.text = message
    m.noticeTimer.control = "stop"
    m.noticeTimer.control = "start"
end sub

sub clearNotice()
    m.notice.text = ""
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "options" and m.inSearch then return false
    if key = "options" or (key = "OK" and m.top.statusText <> "")
        m.top.refreshRequested++
        return true
    end if
    ' Back always bubbles to MainScene, which preserves the existing exit behavior.
    return false
end function

' Refresh progress/metadata on existing nodes; never reset RowList content or focus.
' New titles and changed shelf membership appear after the explicit Options refresh.
sub updateCachedMovies(movies as object)
    m.search.CallFunc("updateCachedMovies", movies)
    if m.rows.content = invalid then return
    m.updatingCache = true
    byId = {}
    for each movie in movies
        byId[HomeItemKey(movie.id)] = movie
    end for
    for rowIndex = 0 to m.rows.content.GetChildCount() - 1
        row = m.rows.content.GetChild(rowIndex)
        for itemIndex = 0 to row.GetChildCount() - 1
            item = row.GetChild(itemIndex)
            key = HomeItemKey(item.movieData.id)
            if byId.DoesExist(key)
                movie = byId[key]
                presentation = MoviePresentation(movie)
                item.movieData = movie
                item.progress = presentation.progress
            end if
        end for
    end for
    m.hero.CallFunc("refreshAction")
    m.updatingCache = false
end sub

function HomeItemKey(id as dynamic) as string
    if GetInterface(id, "ifString") <> invalid then return id
    return id.ToStr()
end function
