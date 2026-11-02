package za.co.topprivateplug;

/** Native stats are deltas (the wrapper resets counters on each read). */
final class TrafficTotals {
    long up, down;
    void add(String report, String tag) {
        if(report == null) throw new IllegalArgumentException("Missing traffic report");
        long nextUp=up, nextDown=down;
        for(String item:report.split(";")) {
            if(item.isEmpty()) continue;
            String[] fields=item.split(",",-1);
            if(fields.length!=3) throw new IllegalArgumentException("Malformed traffic report");
            if(!tag.equals(fields[0])) continue;
            long count=Long.parseLong(fields[2]);
            if(count<0) throw new IllegalArgumentException("Invalid traffic count");
            if("uplink".equals(fields[1])) nextUp=Math.addExact(nextUp,count);
            else if("downlink".equals(fields[1])) nextDown=Math.addExact(nextDown,count);
            else throw new IllegalArgumentException("Invalid traffic direction");
        }
        up=nextUp;down=nextDown;
    }
}
