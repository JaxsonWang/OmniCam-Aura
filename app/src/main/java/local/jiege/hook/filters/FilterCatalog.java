package local.jiege.hook.filters;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Fixed Find X10 filter catalog, shared by the normal and master groups. */
public final class FilterCatalog {
    private static final FilterCatalog INSTANCE = new FilterCatalog();
    private final List<FilterEntry> entries;
    private FilterCatalog() {
        List<FilterEntry> list = new ArrayList<>();
        X10Filters.add(list);
        entries = Collections.unmodifiableList(list);
    }
    public static FilterCatalog get(FilterScope scope) { return INSTANCE; }
    public FilterEntry find(String id) {
        for (FilterEntry entry : entries) if (entry.id.equals(id)) return entry;
        return null;
    }
    public List<FilterEntry> entries() { return entries; }
}
