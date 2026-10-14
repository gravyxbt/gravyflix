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
    print "PASS: Row selection events"
end sub
function childAt(index as integer) as dynamic
    if index < 0 or index >= m.children.Count() then return invalid
    return m.children[index]
end function
sub check(condition as boolean, message as string)
    if not condition then print "FAIL: "; message : stop
end sub
