sub Main()
    m.top = {titleRequested:0,exitRequested:0,exitUp:0,SetFocus:recordFocus,FindNode:findPreview}
    m.keyboard = {text:"iron",SetFocus:recordFocus}
    item = {movieData:{id:1,kind:"movie",title:"Iron Man"},progress:0,title:"Iron Man",metadataLine:"2008"}
    root = {children:[item],GetChild:childAt,GetChildCount:childCount}
    m.grid = {content:root,itemFocused:0,itemSelected:0,visible:true,SetFocus:recordFocus,HasFocus:hasFocus,ownsFocus:true}
    m.actionFocus = {}
    m.delay = {}
    m.layoutDelay = {}
    m.zone = "results"
    m.rebuilding = false
    onResultSelected()
    check(m.top.titleRequested = 1 and m.top.selectedMovie.id = 1, "OK publishes an explicit title command")
    m.grid.ownsFocus = false
    onResultSelected()
    check(m.top.titleRequested = 1, "Hidden grid notifications cannot open titles")
    updateCachedMovies([{id:1,kind:"movie",title:"Iron Man",resume_position:120,duration:1000,cast:["Robert Downey Jr."]}])
    check(m.keyboard.text = "iron" and m.grid.itemFocused = 0, "Background update preserves query and selected result")
    check(m.top.titleRequested = 1, "Background progress update cannot emit a selection")
    check(m.grid.content.children[0].progress = 0.12, "Progress updates without rebuilding result nodes")
    focusSearch()
    check(m.zone = "results" and m.grid.called = true, "Returning from a title focuses the retained results")
    check(onKeyEvent("back",true), "Back from results is handled")
    check(m.zone = "keyboard" and m.keyboard.text = "iron", "Back returns to editing without erasing query")
    check(onKeyEvent("back",true) and m.top.exitRequested = 1, "Back from keyboard exits Search")
    check(onKeyEvent("up",true) and m.top.exitUp = 1, "Keyboard top boundary returns to navigation")
    check(not onKeyEvent("options",true), "Native keyboard Options behavior is preserved")
    check(not onKeyEvent("back",false), "Key releases cannot navigate")
    m.zone = "actions"
    m.actionIndex = 0
    check(onKeyEvent("right",true) and m.actionIndex = 1, "Clear action is reachable")
    check(onKeyEvent("up",true) and m.zone = "keyboard", "Actions can return to the keyboard")
    check(m.top.titleRequested = 1, "Navigation never creates a duplicate selection")
    print "PASS: Search navigation and cache updates"
end sub
function hasFocus() as boolean
    return m.ownsFocus
end function
sub recordFocus(value as boolean)
    m.called = value
end sub
function findPreview(id as string) as object
    return {text:""}
end function
function childAt(index as integer) as dynamic
    if index < 0 or index >= m.children.Count() then return invalid
    return m.children[index]
end function
function childCount() as integer
    return m.children.Count()
end function
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
