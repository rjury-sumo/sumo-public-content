# Log Explorers

## Keyword Log Explorer
A custom dashboard that enables you to start with a search say by category, collector and /or keywords, then drill down to a new search tab only showing surrounding messages.

The new search window will show events from just that source file up to n events, +/- seconds (set in filters) centered on the event matching the search string. Keywords in the new search are included as an "OR" so they are still highlighted but all rows of the log are shown.

Here is how you use it.
1. open the filters panel at the top of the dashboard
2. enter a keyword and optional _sourcecategory.
3. the query panel will update. The link on the right side will open a new search window with just the category string or all meta with your provided query keyword(s).
4. Right click to open a "new Sumo Tab"
select yes/no to include various metadata expressions in the drill down metadata query string. This will open a new search  