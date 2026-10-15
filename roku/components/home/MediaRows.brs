sub init()
    m.list = m.top.FindNode("list")
    m.list.ObserveField("rowItemFocused", "onFocused")
    m.list.ObserveField("rowItemSelected", "onSelected")
end sub

function itemAt(pair as object) as dynamic
    if m.list.content = invalid or pair.Count() < 2 then return invalid
    row = m.list.content.GetChild(pair[0])
    if row = invalid then return invalid
    return row.GetChild(pair[1])
end function

sub onFocused()
    m.top.focusedItem = itemAt(m.list.rowItemFocused)
end sub

sub onSelected()
    item = itemAt(m.list.rowItemSelected)
    if item = invalid then return
    m.top.selectedItem = item
    ' A mutable content node is data, never a selection event.
    m.top.selectionRequested++
end sub

sub focusList()
    m.list.SetFocus(true)
end sub

sub jumpToRow(index as integer)
    m.list.jumpToRowItem = [index, 0]
    m.list.SetFocus(true)
end sub

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    ' Only an unconsumed Up from the top boundary leaves the list.
    if key = "up"
        pair = m.list.rowItemFocused
        if pair.Count() < 2 then return false
        if pair[0] = 0
            m.top.exitUp++
            return true
        end if
    end if
    return false
end function

function captureFocus() as object
    pair = m.list.rowItemFocused
    item = itemAt(pair)
    if item = invalid then return {row:0,column:0,rowKey:"",id:invalid}
    return {row:pair[0],column:pair[1],rowKey:item.homeRowKey,id:item.movieData.id}
end function

sub restoreFocus(anchor as object)
    root = m.list.content
    if root = invalid or root.GetChildCount() = 0 then return
    rowIndex = anchor.row
    if rowIndex >= root.GetChildCount() then rowIndex = root.GetChildCount() - 1
    for i = 0 to root.GetChildCount() - 1
        row = root.GetChild(i)
        if row.GetChildCount() > 0
            if row.GetChild(0).homeRowKey = anchor.rowKey then rowIndex = i
        end if
    end for
    row = root.GetChild(rowIndex)
    if row.GetChildCount() = 0 then return
    column = anchor.column
    if column >= row.GetChildCount() then column = row.GetChildCount() - 1
    for i = 0 to row.GetChildCount() - 1
        if row.GetChild(i).movieData.id = anchor.id then column = i
    end for
    m.list.jumpToRowItem = [rowIndex,column]
    onFocused()
    ' Never SetFocus here: a background history response must not steal focus.
end sub
