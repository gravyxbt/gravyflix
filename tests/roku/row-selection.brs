sub Main()
    item = {movieData:{id:9,title:"Movie"}}
    row = {children:[item],GetChild:childAt}
    root = {children:[row],GetChild:childAt}
    m.list = {content:root,rowItemSelected:[0,0]}
    m.top = {selectionRequested:0}
    onSelected()
    check(m.top.selectionRequested = 1, "Native OK selection emits one command")
    m.top.selectedItem.movieData = {id:9,title:"Refreshed Movie",resume_position:200}
    check(m.top.selectionRequested = 1, "Updating the selected content node is not a new selection")
    onSelected()
    check(m.top.selectionRequested = 2, "Selecting the same card again emits a new command")
    m.list.rowItemSelected = [0,5]
    onSelected()
    check(m.top.selectionRequested = 2, "Invalid selection does not navigate")
    item.homeRowKey = "all"
    root.GetChildCount = childCount
    row.GetChildCount = childCount
    m.list.rowItemFocused = [0,0]
    m.list.SetFocus = rejectFocus
    restoreFocus({row:1,column:0,rowKey:"all",id:9})
    check(m.list.jumpToRowItem[0] = 0 and m.list.jumpToRowItem[1] = 0, "Removing an earlier shelf keeps the same movie selected")
    check(captureFocus().id = 9, "Focus capture uses stable media IDs")
    print "PASS: Row selection events"
end sub
function childAt(index as integer) as dynamic
    if index < 0 or index >= m.children.Count() then return invalid
    return m.children[index]
end function
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub

function childCount() as integer
    return m.children.Count()
end function
sub rejectFocus(flag as boolean)
    print "FAIL: Background shelf updates must not steal remote focus" : stop
end sub
